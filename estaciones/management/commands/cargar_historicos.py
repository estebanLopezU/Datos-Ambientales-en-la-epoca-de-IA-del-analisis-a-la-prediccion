# -*- coding: utf-8 -*-
"""
Carga los datos historicos de los CSV al modelo Lectura.

Uso:
    python manage.py cargar_historicos                 # ambas estaciones
    python manage.py cargar_historicos --estacion 24
    python manage.py cargar_historicos --limite 5000   # prueba rapida
    python manage.py cargar_historicos --desde 2020-01-01

Es idempotente: no vuelve a insertar un (estacion, timestamp) que ya exista,
asi que se puede ejecutar las veces que haga falta. Ademas aplica el mismo
filtrado de valores centinela que el endpoint, para no guardar datos invalidos.
"""
import csv
import os
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from estaciones.api.endpoints import RANGOS, _parse_numero
from estaciones.models import Estacion, Lectura

# Coordenadas de los campus en Manizales (grados decimales).
# La Nubia: 5.029611, -75.472041 (OSM "Campus La Nubia", junto al aeropuerto
#   La Nubia SKMZ 5.029572, -75.464087).
# Palogrande: 5.056879, -75.491379 (OSM "Campus Palogrande", Av. Paralela).
# Fuente: OpenStreetMap/Nominatim; confirmar con la ficha tecnica de cada estacion.
ESTACIONES_INFO = {
    24: {
        "nombre": "La Nubia",
        "campus": "Campus La Nubia - Universidad Nacional de Colombia, Manizales",
        "latitud": 5.029064,
        "longitud": -75.472838,
    },
    29: {
        "nombre": "Palogrande-Postgrados",
        "campus": "Campus Palogrande - Universidad Nacional de Colombia, Manizales",
        "latitud": 5.056879,
        "longitud": -75.491379,
    },
}

VARS = list(RANGOS.keys())
LOTE = 2000


class Command(BaseCommand):
    help = "Carga las lecturas historicas de los CSV de Est_Datos"

    def add_arguments(self, parser):
        parser.add_argument("--estacion", type=int, default=None,
                            help="Codigo de estacion (24 o 29). Por defecto: todas")
        parser.add_argument("--limite", type=int, default=None,
                            help="Maximo de filas por archivo (para pruebas)")
        parser.add_argument("--desde", type=str, default=None,
                            help="Solo filas desde esta fecha YYYY-MM-DD")

    def handle(self, *args, **opciones):
        self.asegurar_estaciones()

        carpeta = settings.BASE_DIR / "Est_Datos"
        if not carpeta.exists():
            self.stderr.write(f"No existe la carpeta: {carpeta}")
            return

        archivos = sorted(carpeta.glob("*.csv"))
        if not archivos:
            self.stderr.write("No hay CSV en Est_Datos")
            return

        for ruta in archivos:
            codigo = self._codigo_desde_nombre(ruta.name)
            if codigo is None:
                self.stdout.write(f"Omitido (nombre no reconocido): {ruta.name}")
                continue
            if opciones["estacion"] and codigo != opciones["estacion"]:
                continue
            self.cargar_archivo(codigo, ruta, opciones)

    def asegurar_estaciones(self):
        for codigo, info in ESTACIONES_INFO.items():
            Estacion.objects.update_or_create(pk=codigo, defaults=info)
        lista = ", ".join(f"{c} ({i['nombre']})"
                          for c, i in ESTACIONES_INFO.items())
        self.stdout.write(f"Estaciones registradas: {lista}")

    @staticmethod
    def _codigo_desde_nombre(nombre):
        """'24-La Nubia.csv' -> 24"""
        cabeza = os.path.splitext(nombre)[0].split("-")[0].strip()
        return int(cabeza) if cabeza.isdigit() else None

    def cargar_archivo(self, codigo, ruta, opciones):
        self.stdout.write("")
        self.stdout.write(f"=== Estacion {codigo} <- {ruta.name} ===")
        try:
            estacion = Estacion.objects.get(pk=codigo)
        except Estacion.DoesNotExist:
            self.stderr.write(f"  Estacion {codigo} no registrada; se omite")
            return

        desde = None
        if opciones["desde"]:
            try:
                desde = datetime.strptime(opciones["desde"], "%Y-%m-%d").date()
            except ValueError:
                self.stderr.write("  --desde no es una fecha valida; se ignora")

        # La idempotencia la garantiza la restriccion unica (estacion,
        # timestamp) junto con ignore_conflicts en bulk_create. OJO: no se
        # puede saltar lo anterior al ultimo timestamp de la base, porque
        # la base puede tener un tramo reciente cargado con --desde y ese
        # atajo se tragaria todo el historico anterior.
        total_antes = Lectura.objects.filter(estacion=estacion).count()

        leidas = intentadas = descartadas = 0
        lote = []

        with open(ruta, newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                if opciones["limite"] and leidas >= opciones["limite"]:
                    break

                fecha = (fila.get("fecha") or "").strip()
                if not fecha:
                    continue
                if desde and fecha < desde.isoformat():
                    continue

                ts = self._timestamp(fecha, (fila.get("tiempo") or "").strip())
                if ts is None:
                    continue
                leidas += 1

                campos = {}
                for var in VARS:
                    if var not in fila:
                        continue
                    valor = _parse_numero(fila[var])
                    if valor is None:
                        continue
                    lo, hi = RANGOS[var]
                    if not (lo <= valor <= hi):
                        descartadas += 1     # centinela o error de sensor
                        continue
                    campos[var] = valor

                lote.append(Lectura(estacion=estacion, timestamp=ts, **campos))
                intentadas += 1

                if len(lote) >= LOTE:
                    Lectura.objects.bulk_create(lote, batch_size=1000,
                                                ignore_conflicts=True)
                    lote = []

        if lote:
            Lectura.objects.bulk_create(lote, batch_size=1000,
                                        ignore_conflicts=True)

        # Con ignore_conflicts no se sabe cuantas chocaron: se mide con el
        # conteo real antes y despues. Es exacto y no gasta memoria.
        total_bd = Lectura.objects.filter(estacion=estacion).count()
        nuevas = total_bd - total_antes
        self.stdout.write(f"  filas leidas          : {leidas:,}")
        self.stdout.write(f"  lecturas nuevas       : {nuevas:,}")
        self.stdout.write(f"  ya en base (ignoradas): {intentadas - nuevas:,}")
        self.stdout.write(f"  valores descartados   : {descartadas:,}"
                          "  (fuera de rango / centinela)")
        self.stdout.write(f"  total en base         : {total_bd:,}")

    @staticmethod
    def _timestamp(fecha, hora):
        """Combina fecha y hora del CSV en un datetime con zona horaria."""
        texto = f"{fecha} {hora or '00:00:00'}"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                ingenuo = datetime.strptime(texto, fmt)
            except ValueError:
                continue
            return timezone.make_aware(ingenuo, timezone.get_current_timezone())
        return None

