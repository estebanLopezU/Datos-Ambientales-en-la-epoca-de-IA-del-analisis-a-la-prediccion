# -*- coding: utf-8 -*-
"""
Pruebas del endpoint de recepcion.

Se ejecutan con:
    python manage.py test estaciones

Usan el cliente de pruebas de Django y una base temporal: no tocan db.sqlite3.
"""
from django.test import TestCase

from estaciones.models import Estacion, Lectura

URL_DATOS = "/api/v1/estaciones/datos/"

LECTURA_VALIDA = {
    "estacion": 24,
    "timestamp": "2026-10-07 22:30:00",
    "temperatura": 18.4,
    "humedad_relativa": 88,
    "precipitacion": 0.0,
    "presion_barometrica": 600.5,
    "velocidad_viento": 1.2,
    "direccion_viento": 110,
    "radiacion_solar": 0.0,
    "evapotranspiracion": 0.0,
}


class EndpointRecepcionTests(TestCase):
    def setUp(self):
        Estacion.objects.create(pk=24, nombre="La Nubia", campus="La Nubia")
        Estacion.objects.create(pk=29, nombre="Palogrande",
                                campus="Palogrande-Postgrados")

    def post(self, datos, **extra):
        return self.client.post(URL_DATOS, data=datos,
                                content_type="application/json", **extra)

    # --- casos que deben funcionar ---

    def test_guarda_lectura_valida(self):
        r = self.post(LECTURA_VALIDA)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Lectura.objects.count(), 1)
        self.assertTrue(r.json()["ok"])

    def test_get_devuelve_documentacion(self):
        r = self.client.get(URL_DATOS)
        self.assertEqual(r.status_code, 200)
        self.assertIn("variables_aceptadas", r.json())

    def test_acepta_lote(self):
        lote = [dict(LECTURA_VALIDA, timestamp=f"2026-10-07 22:{m:02d}:00")
                for m in range(10)]
        r = self.post(lote)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Lectura.objects.count(), 10)

    def test_acepta_timestamp_iso(self):
        r = self.post(dict(LECTURA_VALIDA, timestamp="2026-10-07T22:30:00"))
        self.assertEqual(r.status_code, 201)

    def test_acepta_coma_decimal(self):
        r = self.post(dict(LECTURA_VALIDA, temperatura="18,4"))
        self.assertEqual(r.status_code, 201)
        self.assertAlmostEqual(Lectura.objects.first().temperatura, 18.4, places=3)

    def test_nombre_alternativo_de_estacion(self):
        r = self.post({"codigo": 29, "timestamp": "2026-10-07 22:30:00",
                       "temperatura": 17.0})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Lectura.objects.get().estacion_id, 29)

    # --- idempotencia: lo mas importante del endpoint ---

    def test_reenviar_no_duplica(self):
        self.post(LECTURA_VALIDA)
        r = self.post(LECTURA_VALIDA)
        self.assertEqual(Lectura.objects.count(), 1)
        self.assertEqual(r.json()["duplicadas"], 1)

    def test_lote_con_duplicados_parciales(self):
        lote = [dict(LECTURA_VALIDA, timestamp=f"2026-10-07 22:{m:02d}:00")
                for m in range(5)]
        self.post(lote)
        r = self.post(lote)
        self.assertEqual(Lectura.objects.count(), 5)
        self.assertEqual(r.json()["duplicadas"], 5)

    # --- validacion de valores centinela ---

    def test_rechaza_humedad_255(self):
        r = self.post(dict(LECTURA_VALIDA, humedad_relativa=255))
        # La lectura se guarda, pero con aviso => 207, no 201.
        self.assertEqual(r.status_code, 207)
        self.assertIsNone(Lectura.objects.get().humedad_relativa)  # el valor no
        self.assertTrue(r.json()["rechazados"])

    def test_rechaza_viento_imposible(self):
        self.post(dict(LECTURA_VALIDA, velocidad_viento=113.99))
        self.assertIsNone(Lectura.objects.get().velocidad_viento)

    def test_rechaza_presion_cero(self):
        self.post(dict(LECTURA_VALIDA, presion_barometrica=0))
        self.assertIsNone(Lectura.objects.get().presion_barometrica)

    def test_rechaza_direccion_mayor_a_360(self):
        self.post(dict(LECTURA_VALIDA, direccion_viento=507))
        self.assertIsNone(Lectura.objects.get().direccion_viento)

    def test_guarda_el_resto_si_un_sensor_falla(self):
        r = self.post(dict(LECTURA_VALIDA, temperatura=999))
        self.assertEqual(r.status_code, 207)       # se guardo, con una advertencia
        lec = Lectura.objects.get()
        self.assertIsNone(lec.temperatura)
        self.assertAlmostEqual(lec.presion_barometrica, 600.5, places=3)
        self.assertEqual(r.json()["creadas"], 1)

    # --- peticiones invalidas ---

    def test_rechaza_json_malformado(self):
        r = self.client.post(URL_DATOS, data="{no es json",
                              content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_rechaza_lista_vacia(self):
        self.assertEqual(self.post([]).status_code, 400)

    def test_rechaza_estacion_desconocida(self):
        r = self.post(dict(LECTURA_VALIDA, estacion=99))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Lectura.objects.count(), 0)

    def test_rechaza_sin_estacion(self):
        datos = {k: v for k, v in LECTURA_VALIDA.items() if k != "estacion"}
        self.assertEqual(self.post(datos).status_code, 400)

    def test_rechaza_sin_timestamp(self):
        datos = {k: v for k, v in LECTURA_VALIDA.items() if k != "timestamp"}
        self.assertEqual(self.post(datos).status_code, 400)

    def test_rechaza_timestamp_invalido(self):
        self.assertEqual(
            self.post(dict(LECTURA_VALIDA, timestamp="cualquier cosa")).status_code,
            400)

    def test_no_acepta_delete(self):
        self.assertEqual(self.client.delete(URL_DATOS).status_code, 405)

URL_PRONOSTICO = "/api/v1/estaciones/pronostico/"


class EndpointPronosticoTests(TestCase):
    """Pruebas del endpoint de pronostico (Open-Meteo).

    No se llama a la API externa: solo se verifican las respuestas que no
    dependen de la red (validacion del parametro y estacion sin coordenadas).
    """

    def test_rechaza_estacion_invalida(self):
        r = self.client.get(URL_PRONOSTICO, {"estacion": "xyz"})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_estacion_inexistente(self):
        r = self.client.get(URL_PRONOSTICO, {"estacion": 99})
        self.assertEqual(r.status_code, 400)

    def test_404_si_la_estacion_no_tiene_coordenadas(self):
        Estacion.objects.create(codigo=24, nombre="La Nubia",
                                campus="La Nubia")
        r = self.client.get(URL_PRONOSTICO, {"estacion": 24})
        self.assertEqual(r.status_code, 404)

URL_HISTORIAL = "/api/v1/estaciones/historial/"


class EndpointHistorialTests(TestCase):
    """Pruebas del historial estadistico (drill-down ano/mes/dia/hora).

    Se crean lecturas en fechas concretas para verificar cada nivel y que
    las cascadas invalidas se rechacen con 400.
    """

    def setUp(self):
        # La vista cachea las respuestas del historial; sin esto, una
        # prueba podria ver el cache de otra con los mismos parametros.
        from django.core.cache import cache
        cache.clear()

    @staticmethod
    def _sembrar():
        est = Estacion.objects.create(codigo=24, nombre="La Nubia",
                                      campus="La Nubia")        # Dos anos, dos meses del 2026, y tres dias del sept.
        stamps = [
            "2026-09-01 10:00:00", "2026-09-01 11:00:00",
            "2026-09-02 10:00:00",
            "2026-10-05 10:00:00",
            "2025-03-10 10:00:00",
        ]
        import datetime as dt
        from django.utils import timezone as dj_tz
        zona = dt.timezone(dt.timedelta(hours=-5))   # America/Bogota fija
        for s in stamps:
            Lectura.objects.create(
                estacion=est,
                timestamp=dj_tz.make_aware(dt.datetime.fromisoformat(s), zona),
                temperatura=18.0, precipitacion=0.5)
        return est

    def test_rechaza_estacion_invalida(self):
        r = self.client.get(URL_HISTORIAL, {"estacion": "xyz"})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_estacion_inexistente(self):
        r = self.client.get(URL_HISTORIAL, {"estacion": 99})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_mes_sin_anio(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24, "mes": 9})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_dia_sin_mes(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24,
                                            "anio": 2026, "dia": 15})
        self.assertEqual(r.status_code, 400)

    def test_rechaza_parametros_fuera_de_rango(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24, "mes": 13})
        self.assertEqual(r.status_code, 400)

    def test_nivel_anios_lista_los_anios_con_datos(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24})
        d = r.json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["nivel"], "anio")
        self.assertEqual([f["etiqueta"] for f in d["filas"]],
                         ["2025", "2026"])

    def test_nivel_meses_agrega_lluvia(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24, "anio": 2026})
        d = r.json()
        self.assertEqual(d["nivel"], "mes")
        filas = {f["etiqueta"]: f for f in d["filas"]}
        self.assertEqual(filas["sep 2026"]["lluvia"], 1.5)   # 3 lecturas x0,5
        self.assertEqual(filas["oct 2026"]["lluvia"], 0.5)

    def test_nivel_dias(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24,
                                            "anio": 2026, "mes": 9})
        d = r.json()
        self.assertEqual(d["nivel"], "dia")
        self.assertEqual(len(d["filas"]), 2)                # dias 1 y 2

    def test_nivel_horas(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24,
                                            "anio": 2026, "mes": 9, "dia": 1})
        d = r.json()
        self.assertEqual(d["nivel"], "hora")
        self.assertEqual([f["etiqueta"] for f in d["filas"]],
                         ["10:00", "11:00"])

    def test_crudos_exigen_fecha_completa(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24, "crudos": "1"})
        self.assertEqual(r.status_code, 400)

    def test_crudos_del_dia(self):
        self._sembrar()
        r = self.client.get(URL_HISTORIAL, {"estacion": 24, "anio": 2026,
                                            "mes": 9, "dia": 1, "crudos": "1"})
        d = r.json()
        self.assertEqual(d["nivel"], "crudos")
        self.assertEqual(len(d["filas"]), 2)
        self.assertTrue(all("t" in f for f in d["filas"]))

    def test_agrupacion_no_rompe_el_cursor_debug(self):
        """Regresion: con DEBUG=True el cursor de SQLite interpola la
        consulta con sql % params; el %%Y de los formatos debe llegarle
        como %% para que no reviente. Reproduce el bug que solo saltaba
        con runserver (DEBUG=True) y no en las pruebas (DEBUG=False).
        """
        from django.test.utils import override_settings
        from django.db import connection
        from estaciones.views import _agrupar_por_cubo
        self._sembrar()
        with override_settings(DEBUG=True):
            with connection.cursor():      # asegura wrapper debug activo
                pass
            est = Estacion.objects.get(pk=24)
            filas = list(_agrupar_por_cubo(
                Lectura.objects.filter(estacion=est), "anio"))
        # La semilla tiene lecturas de 2025 y 2026: dos cubos de ano.
        self.assertEqual([f["cubo"] for f in filas],
                         ["2025", "2026"])
