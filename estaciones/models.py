# -*- coding: utf-8 -*-
"""
Modelos de datos para las estaciones meteorologicas UNAL sede Manizales.

Las estaciones son:
  - 24: La Nubia (campus principal)
  - 29: Palogrande-Postgrados

Las unidades se infieren de la nomenclatura estandar usada por la red
(ver Excel_Organizado/README.md): conviene confirmarlas con la ficha tecnica.
"""
from django.db import models


class Estacion(models.Model):
    """Estacion meteorologica fija."""

    codigo = models.PositiveSmallIntegerField(
        primary_key=True,
        verbose_name="codigo",
        help_text="24 = La Nubia, 29 = Palogrande-Postgrados",
    )
    nombre = models.CharField(max_length=100)
    campus = models.CharField(max_length=100)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Grados decimales, positivo al norte",
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Grados decimales, negativo al oeste",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "estacion"
        verbose_name_plural = "estaciones"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class ConsolaAmbient(models.Model):
    """Inventario de consolas Ambient/Ecowitt vistas en la red local.

    Cada consola se identifica por el parametro ID que manda en cada
    reporte Wunderground (ej. LUNA). La estacion 99 historica se conserva
    como consola por defecto para no romper el panel existente.
    """

    device_id = models.CharField(
        primary_key=True, max_length=64,
        help_text="Parametro ID del reporte Wunderground (ej. LUNA)",
    )
    nombre = models.CharField(max_length=100)
    estacion = models.OneToOneField(
        Estacion, on_delete=models.CASCADE, related_name="consola",
        null=True, blank=True,
        help_text="Estacion logica donde se guardan sus lecturas",
    )
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    software = models.CharField(max_length=100, null=True, blank=True)
    ultimo_reporte = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Hora de llegada del ultimo reporte recibido",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "consola Ambient"
        verbose_name_plural = "consolas Ambient"
        ordering = ["device_id"]

    def __str__(self):
        return f"{self.device_id} - {self.nombre}"


class Lectura(models.Model):
    """
    Una lectura de una estacion en un instante.

    Es la tabla que alimenta el endpoint de recepcion y el dashboard.
    timestamp viene de la estacion (no de now()): asi se respeta el reloj del
    datalogger y se pueden reprocesar datos historicos sin duplicarlos.
    """

    estacion = models.ForeignKey(
        Estacion, on_delete=models.CASCADE, related_name="lecturas"
    )
    timestamp = models.DateTimeField(
        db_index=True, help_text="Instante de la medicion, segun la estacion"
    )
    recibido = models.DateTimeField(
        auto_now_add=True, help_text="Instante en que el servidor la recibio"
    )

    # Variables medidas. null/blank = la estacion no reporto ese valor.
    temperatura = models.FloatField(null=True, blank=True, help_text="grados Celsius")
    humedad_relativa = models.FloatField(
        null=True, blank=True, help_text="porcentaje 0-100"
    )
    precipitacion = models.FloatField(null=True, blank=True, help_text="milimetros")
    presion_barometrica = models.FloatField(null=True, blank=True, help_text="hPa")
    velocidad_viento = models.FloatField(null=True, blank=True, help_text="m/s")
    direccion_viento = models.FloatField(
        null=True, blank=True, help_text="grados 0-360"
    )
    radiacion_solar = models.FloatField(null=True, blank=True, help_text="W/m2")
    evapotranspiracion = models.FloatField(null=True, blank=True, help_text="milimetros")

    # Extras solo para la estacion 99 (Ambient/Ecowitt). Las 24/29 los dejan
    # en NULL: asi el historico de La Nubia/Palogrande no se toca.
    temperatura_interior = models.FloatField(null=True, blank=True, help_text="grados Celsius (sensor indoor)")
    humedad_interior = models.FloatField(null=True, blank=True, help_text="porcentaje 0-100 (sensor indoor)")
    racha_viento = models.FloatField(null=True, blank=True, help_text="m/s (windgust)")
    viento_promedio_10m = models.FloatField(null=True, blank=True, help_text="m/s (avg 10 min)")
    indice_uv = models.FloatField(null=True, blank=True, help_text="indice UV 0-15")
    presion_absoluta = models.FloatField(null=True, blank=True, help_text="hPa absoluta (baromabs)")
    lluvia_tasa = models.FloatField(null=True, blank=True, help_text="mm/h (rain rate)")
    lluvia_hora = models.FloatField(null=True, blank=True, help_text="mm ultima hora")
    lluvia_dia = models.FloatField(null=True, blank=True, help_text="mm acumulado dia")
    lluvia_semana = models.FloatField(null=True, blank=True, help_text="mm acumulado semana")
    lluvia_mes = models.FloatField(null=True, blank=True, help_text="mm acumulado mes")
    lluvia_anio = models.FloatField(null=True, blank=True, help_text="mm acumulado anio")
    lluvia_evento = models.FloatField(null=True, blank=True, help_text="mm evento actual")

    # No se almacenan nivel, caudal ni brillo: en los CSV historicos son
    # siempre 0 o estan completamente vacios (ver README de Excel_Organizado).

    class Meta:
        verbose_name = "lectura"
        verbose_name_plural = "lecturas"
        ordering = ["-timestamp"]
        # Una estacion no puede tener dos lecturas en el mismo instante.
        # Es la garantia de idempotencia del endpoint: reenviar un dato no duplica.
        constraints = [
            models.UniqueConstraint(
                fields=["estacion", "timestamp"],
                name="uniq_lectura_estacion_timestamp",
            )
        ]
        indexes = [
            # Cubre la consulta estrella del dashboard:
            # "ultimas 24 h de la estacion X, de lo mas nuevo a lo mas viejo".
            models.Index(
                fields=["estacion", "-timestamp"],
                name="ix_lectura_estacion_ts_desc",
            ),
        ]

    def __str__(self):
        return f"{self.estacion.codigo} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"
