# -*- coding: utf-8 -*-
"""Pruebas del modulo Ambient (estacion 99, aislada de 24/29)."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from estaciones.models import ConsolaAmbient, Estacion, Lectura
from estaciones.api.ambient import (
    AMBIENT_CODIGO, dispositivo_desde_params, estacion_ambient,
    traducir_ambient,
)
from estaciones.api import ambient_vistas


class TraducirAmbientTest(TestCase):
    def test_convierte_unidades(self):
        campos, adv = traducir_ambient({
            "tempf": "77.0", "humidity": "80",
            "baromin": "29.53", "windspeedmph": "5",
            "winddir": "90", "solarradiation": "500",
            "hourlyrainin": "0.1",
            "dateutc": "2026-10-14 19:30:00",
        })
        self.assertEqual(campos["temperatura"], 25.0)
        self.assertEqual(campos["humedad_relativa"], 80.0)
        self.assertAlmostEqual(campos["presion_barometrica"], 1000.0, delta=1.0)
        # QNH (~1013 hPa) se guarda tal cual aunque supere el RANGOS de
        # estacion (~600 hPa en Manizales): es presion a nivel del mar.
        self.assertGreater(campos["presion_barometrica"], 900.0)
        self.assertAlmostEqual(campos["velocidad_viento"], 2.2, delta=0.1)
        self.assertEqual(campos["direccion_viento"], 90.0)
        self.assertEqual(campos["radiacion_solar"], 500.0)
        self.assertAlmostEqual(campos["precipitacion"], 2.5, delta=0.1)

    def test_descarta_fuera_de_rango(self):
        campos, adv = traducir_ambient({"tempf": "300"})
        self.assertNotIn("temperatura", campos)
        self.assertTrue(adv)

    def test_campos_extras_consola(self):
        campos, _adv = traducir_ambient({
            "tempf": "71.6", "humidity": "74",
            "tempinf": "75.0", "humidityin": "50",
            "windspeedmph": "5.6", "winddir": "319",
            "windgustmph": "8.1", "windspdmph_avg10m": "8.1",
            "uv": "8", "solarradiation": "881.8",
            "baromin": "29.5", "baromabsin": "26.0",
            "rainratein": "0.0", "eventrainin": "0.0",
            "hourlyrainin": "0.0", "dailyrainin": "5.206",
            "weeklyrainin": "5.206", "monthlyrainin": "8.661",
            "yearlyrainin": "14.331",
            "dateutc": "2026-10-14 16:49:25",
        })
        self.assertAlmostEqual(campos["temperatura_interior"], 23.9, delta=0.2)
        self.assertEqual(campos["humedad_interior"], 50.0)
        self.assertAlmostEqual(campos["racha_viento"], 3.6, delta=0.2)
        self.assertAlmostEqual(campos["viento_promedio_10m"], 3.6, delta=0.2)
        self.assertEqual(campos["indice_uv"], 8.0)
        self.assertAlmostEqual(campos["lluvia_dia"], 132.2, delta=0.5)
        self.assertAlmostEqual(campos["lluvia_mes"], 220.0, delta=0.5)
        self.assertAlmostEqual(campos["lluvia_anio"], 364.0, delta=0.5)
        self.assertGreater(campos["presion_absoluta"], 800.0)

    def test_receptor_guarda_extras(self):
        r = self.client.get("/weatherstation/updateweatherstation.php", {
            "tempf": "71.6", "humidity": "74", "tempinf": "75.0",
            "windspeedmph": "5.6", "windgustmph": "8.1", "uv": "8",
            "dailyrainin": "5.206", "dateutc": "2026-10-14 16:49:25",
        })
        self.assertEqual(r.status_code, 200)
        lec = Lectura.objects.get(estacion__codigo=AMBIENT_CODIGO)
        self.assertIsNotNone(lec.racha_viento)
        self.assertIsNotNone(lec.temperatura_interior)
        self.assertIsNotNone(lec.lluvia_dia)


class ReceptorAmbientTest(TestCase):
    def test_recibe_y_responde_success(self):
        r = self.client.get("/weatherstation/updateweatherstation.php", {
            "tempf": "77.0", "humidity": "80", "baromin": "29.53",
            "windspeedmph": "5", "winddir": "90",
            "solarradiation": "500", "hourlyrainin": "0",
            "dateutc": "2026-10-14 19:30:00",
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn("success", r.content.decode())
        self.assertEqual(
            Lectura.objects.filter(estacion__codigo=AMBIENT_CODIGO).count(), 1)

    def test_idempotente_mismo_dateutc(self):
        q = {"tempf": "77.0", "humidity": "80",
             "dateutc": "2026-10-14 19:30:00"}
        self.client.get("/weatherstation/updateweatherstation.php", q)
        r = self.client.get("/weatherstation/updateweatherstation.php", q)
        self.assertEqual(r["X-Ambient-Estado"], "duplicada")
        self.assertEqual(
            Lectura.objects.filter(estacion__codigo=AMBIENT_CODIGO).count(), 1)

    def test_sin_datos_400(self):
        r = self.client.get("/weatherstation/updateweatherstation.php")
        self.assertEqual(r.status_code, 400)

    def test_no_toca_24_29(self):
        for cod in (24, 29):
            Estacion.objects.create(codigo=cod, nombre=f"E{cod}",
                                    campus="UNAL")
        antes_24 = Lectura.objects.filter(estacion__codigo=24).count()
        antes_29 = Lectura.objects.filter(estacion__codigo=29).count()
        self.client.get("/weatherstation/updateweatherstation.php", {
            "tempf": "77.0", "humidity": "80",
            "dateutc": "2026-10-14 19:30:00"})
        self.assertEqual(
            Lectura.objects.filter(estacion__codigo=24).count(), antes_24)
        self.assertEqual(
            Lectura.objects.filter(estacion__codigo=29).count(), antes_29)

    def test_panel_y_apis_aisladas(self):
        self.client.get("/weatherstation/updateweatherstation.php", {
            "tempf": "77.0", "humidity": "80",
            "dateutc": "2026-10-14 19:30:00"})
        self.assertEqual(self.client.get("/ambient/").status_code, 200)
        u = self.client.get("/api/v1/ambient/ultima/").json()
        self.assertTrue(u["disponible"])
        self.assertEqual(u["codigo"], AMBIENT_CODIGO)
        s = self.client.get("/api/v1/ambient/serie/").json()
        self.assertEqual(s["codigo"], AMBIENT_CODIGO)
        self.assertEqual(s["n"], 1)
        # Las APIs originales no ven al 99.
        orig = self.client.get("/api/v1/estaciones/ultima/").json()
        self.assertNotIn("99", orig.get("estaciones", {}))


class RedAmbientTest(TestCase):
    def test_id_del_dispositivo(self):
        self.assertEqual(
            dispositivo_desde_params({"ID": "LUNA", "tempf": "77"}), "LUNA")
        self.assertEqual(
            dispositivo_desde_params({"tempf": "77"}), "DESCONOCIDA")
        # El placeholder de pruebas no crea consolas fantasma.
        self.assertEqual(dispositivo_desde_params({"ID": "x"}), "DESCONOCIDA")

    def test_receptor_registra_consola(self):
        r = self.client.get("/weatherstation/updateweatherstation.php", {
            "ID": "LUNA", "PASSWORD": "LUNA", "tempf": "77.0",
            "humidity": "60", "dateutc": "2026-10-15 12:00:00",
        })
        self.assertEqual(r.status_code, 200)
        consola = ConsolaAmbient.objects.get(device_id="LUNA")
        self.assertIsNotNone(consola.ultimo_reporte)
        self.assertEqual(consola.estacion_id, AMBIENT_CODIGO)

    def test_api_consolas_en_linea_y_offline(self):
        self.client.get("/weatherstation/updateweatherstation.php", {
            "ID": "LUNA", "tempf": "77.0", "humidity": "60",
            "dateutc": "2026-10-15 12:00:00",
        })
        vieja = ConsolaAmbient.objects.create(
            device_id="VIEJA", nombre="VIEJA",
            ultimo_reporte=timezone.now() - timedelta(hours=2))
        j = self.client.get("/api/v1/ambient/consolas/").json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["n"], 2)
        por_id = {c["device_id"]: c for c in j["consolas"]}
        self.assertTrue(por_id["LUNA"]["en_linea"])
        self.assertFalse(por_id["VIEJA"]["en_linea"])
        self.assertIsNotNone(por_id["LUNA"]["temperatura"])

    def test_panel_red_y_detalle(self):
        self.client.get("/weatherstation/updateweatherstation.php", {
            "ID": "LUNA", "tempf": "77.0", "humidity": "60",
            "dateutc": "2026-10-15 12:00:00",
        })
        r = self.client.get("/ambient/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "LUNA")
        d = self.client.get("/ambient/", {"consola": "LUNA"})
        self.assertEqual(d.status_code, 200)
        self.assertContains(d, "LUNA")


class SondeoRedTest(TestCase):
    """El badge EN LINEA tambien mira la red, no solo los datos."""

    def _alcanzable(self, resultado):
        return patch.object(ambient_vistas, "_tcp_responde",
                            return_value=False), \
               patch.object(ambient_vistas, "_ping", return_value=resultado)

    def test_sin_ip_no_se_puede_saber(self):
        self.assertIsNone(ambient_vistas._alcanzable(None))
        self.assertIsNone(ambient_vistas._alcanzable(""))

    def test_ping_respuesta_y_fallo(self):
        tcp, ping = self._alcanzable(True)
        with tcp, ping:
            self.assertTrue(ambient_vistas._alcanzable("192.168.137.245"))
        tcp, ping = self._alcanzable(False)
        with tcp, ping:
            self.assertFalse(ambient_vistas._alcanzable("192.168.137.246"))

    def test_ping_indeterminado_devuelve_none(self):
        tcp, ping = self._alcanzable(None)
        with tcp, ping:
            self.assertIsNone(ambient_vistas._alcanzable("192.168.137.247"))

    def test_cache_no_repite_el_sondeo(self):
        ip = "192.168.137.248"
        with patch.object(ambient_vistas, "_tcp_responde",
                          return_value=False) as tcp, \
                patch.object(ambient_vistas, "_ping",
                             return_value=True) as ping:
            primera = ambient_vistas._alcanzable(ip)
            segunda = ambient_vistas._alcanzable(ip)     # servida del cache
        self.assertTrue(primera)
        self.assertTrue(segunda)
        # Un solo sondeo real para las dos llamadas (TTL de 30 s).
        self.assertEqual(tcp.call_count, 1)
        self.assertEqual(ping.call_count, 1)

    def test_estado_reportando(self):
        c = ConsolaAmbient.objects.create(
            device_id="VIVA", nombre="VIVA", ip_origen="192.168.137.10",
            ultimo_reporte=timezone.now())
        en_linea, motivo, hace = ambient_vistas.estado_red(c)
        self.assertTrue(en_linea)
        self.assertEqual(motivo, "reporte")
        self.assertLessEqual(hace, 60)

    def test_estado_conectada_sin_datos(self):
        vieja = ConsolaAmbient.objects.create(
            device_id="CALLADA", nombre="CALLADA",
            ip_origen="192.168.137.11",
            ultimo_reporte=timezone.now() - timedelta(days=5))
        with patch.object(ambient_vistas, "_alcanzable", return_value=True):
            en_linea, motivo, _ = ambient_vistas.estado_red(vieja)
        # El punto de todo: conectada a la red pero sin enviar lecturas.
        self.assertTrue(en_linea)
        self.assertEqual(motivo, "red")
        self.assertEqual(ambient_vistas.estado_texto(motivo),
                         "EN LINEA · sin datos")

    def test_estado_sin_conexion(self):
        muerta = ConsolaAmbient.objects.create(
            device_id="MUERTA", nombre="MUERTA",
            ip_origen="192.168.137.12",
            ultimo_reporte=timezone.now() - timedelta(days=5))
        with patch.object(ambient_vistas, "_alcanzable", return_value=False):
            en_linea, motivo, _ = ambient_vistas.estado_red(muerta)
        self.assertFalse(en_linea)
        self.assertEqual(motivo, "sin-red")

    def test_estado_desconocido_sin_sondeo(self):
        # Vercel no alcanza la LAN: se queda con el veredicto de los datos.
        remota = ConsolaAmbient.objects.create(
            device_id="REMOTA", nombre="REMOTA",
            ip_origen="192.168.137.13",
            ultimo_reporte=timezone.now() - timedelta(days=5))
        with patch.object(ambient_vistas, "_alcanzable", return_value=None):
            en_linea, motivo, _ = ambient_vistas.estado_red(remota)
        self.assertFalse(en_linea)
        self.assertEqual(motivo, "desconocido")
        self.assertEqual(ambient_vistas.estado_texto(motivo),
                         "SIN DATOS RECIENTES")

    def test_estado_nunca_reporto(self):
        nueva = ConsolaAmbient.objects.create(device_id="NUEVA", nombre="NUEVA")
        en_linea, motivo, _ = ambient_vistas.estado_red(nueva)
        self.assertFalse(en_linea)
        self.assertEqual(motivo, "nunca")

    def test_panel_detalle_muestra_conectada_sin_datos(self):
        # LUNA con la ultima lectura vieja pero viva en la red.
        est = estacion_ambient()
        Lectura.objects.create(
            estacion=est, timestamp=timezone.now() - timedelta(days=3),
            temperatura=21.6, humedad_relativa=70.0, velocidad_viento=1.2)
        ConsolaAmbient.objects.create(
            device_id="LUNA", nombre="LUNA", estacion=est,
            ip_origen="192.168.137.245",
            ultimo_reporte=timezone.now() - timedelta(days=3))
        with patch.object(ambient_vistas, "_alcanzable", return_value=True):
            r = self.client.get("/ambient/", {"consola": "LUNA"})
        self.assertContains(r, "EN LINEA · sin datos")

    def test_api_ultima_incluye_veredicto(self):
        est = estacion_ambient()
        Lectura.objects.create(
            estacion=est, timestamp=timezone.now() - timedelta(days=3),
            temperatura=21.6, humedad_relativa=70.0)
        ConsolaAmbient.objects.create(
            device_id="LUNA", nombre="LUNA", estacion=est,
            ip_origen="192.168.137.245",
            ultimo_reporte=timezone.now() - timedelta(days=3))
        with patch.object(ambient_vistas, "_alcanzable", return_value=True):
            j = self.client.get("/api/v1/ambient/ultima/").json()
        self.assertTrue(j["en_linea"])
        self.assertEqual(j["motivo"], "red")
        self.assertEqual(j["estado_txt"], "EN LINEA · sin datos")
