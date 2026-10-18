
# -*- coding: utf-8 -*-
"""Vistas HTTP del modulo Ambient (receptor + APIs propias aisladas)."""
import math

from estaciones.api.ambient import (
    AMBIENT_CODIGO, dispositivo_desde_params, estacion_ambient,
    traducir_ambient,
)

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from estaciones.models import ConsolaAmbient, Estacion, Lectura

# Minutos sin reportar para considerar una consola fuera de linea.
UMBRAL_OFFLINE_MIN = 10


def _rocio(t, hr):
    """Punto de rocio (C) con la aproximacion de Magnus."""
    if t is None or hr is None or not (0 < hr <= 100):
        return None
    try:
        g = math.log(hr / 100.0) + (17.62 * t) / (243.12 + t)
        return round(243.12 * g / (17.62 - g), 1)
    except (ValueError, ZeroDivisionError):
        return None


def _sensacion(t, hr, v_ms):
    """Aparente: calor si >=27C, viento frio si <=10C, si no el aire."""
    if t is None:
        return None
    if t >= 27 and hr is not None:
        tf = t * 9 / 5 + 32
        hi = (-42.379 + 2.04901523 * tf + 10.14333127 * hr
              - 0.22475541 * tf * hr - 0.00683783 * tf ** 2
              - 0.05481717 * hr ** 2 + 0.00122874 * tf ** 2 * hr
              + 0.00085282 * tf * hr ** 2 - 0.00000199 * tf ** 2 * hr ** 2)
        return round(max((hi - 32) * 5 / 9, t), 1)
    if t <= 10 and v_ms is not None:
        v_kmh = v_ms * 3.6
        if v_kmh >= 4.8:
            wc = (13.12 + 0.6215 * t - 11.37 * v_kmh ** 0.16
                  + 0.3965 * t * v_kmh ** 0.16)
            return round(min(wc, t), 1)
    return round(t, 1)


@csrf_exempt
@require_GET
def ambient_recibir(request):
    """GET /weatherstation/updateweatherstation.php — receptor Ambient."""
    params = request.GET.dict()
    if not params:
        return HttpResponse("no data\n", status=400, content_type="text/plain")

    campos, advertencias = traducir_ambient(params)

    est = estacion_ambient()
    _registrar_consola(request, params, est)
    metricas = {k: v for k, v in campos.items() if k != "timestamp"}
    if not metricas:
        # La consola llego (enlace OK) pero sin sensores validos
        # (ej. todo en -9999 al reconectar): se avisa sin tumbarla.
        return HttpResponse("nodata: sin sensores validos\n", status=200,
                            content_type="text/plain")
    _obj, creada = Lectura.objects.get_or_create(
        estacion=est,
        timestamp=campos["timestamp"],
        defaults=metricas,
    )
    resp = "success\n"
    if advertencias:
        resp += "warnings: " + "; ".join(advertencias) + "\n"
    r = HttpResponse(resp, content_type="text/plain", status=200)
    r["X-Ambient-Estado"] = "creada" if creada else "duplicada"
    return r


def _ip_cliente(request):
    """IP real de la consola (respeta X-Forwarded-For si hay proxy)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


def _registrar_consola(request, params, est):
    """Upsert del inventario: cada ID que reporta queda registrado."""
    device_id = dispositivo_desde_params(params)
    ahora = timezone.now()
    ip = _ip_cliente(request)
    bajas = {str(k).lower(): v for k, v in params.items()}
    software = (bajas.get("softwaretype") or "").strip() or None
    consola, _ = ConsolaAmbient.objects.get_or_create(
        device_id=device_id,
        defaults={"nombre": device_id, "estacion": est},
    )
    cambios = {"ultimo_reporte": ahora}
    if consola.estacion_id is None:
        cambios["estacion"] = est
    if ip:
        cambios["ip_origen"] = ip
    if software:
        cambios["software"] = software[:100]
    for campo, valor in cambios.items():
        setattr(consola, campo, valor)
    consola.save(update_fields=[*cambios.keys()])


def _resumen_consola(consola):
    """Ficha de una consola para el panel de red."""
    ahora = timezone.now()
    hace_seg = None
    en_linea = False
    if consola.ultimo_reporte is not None:
        hace_seg = int((ahora - consola.ultimo_reporte).total_seconds())
        en_linea = hace_seg <= UMBRAL_OFFLINE_MIN * 60
    resumen = {"temperatura": None, "humedad_relativa": None,
               "velocidad_viento": None, "timestamp": None}
    if consola.estacion_id is not None:
        ult = (Lectura.objects.filter(estacion_id=consola.estacion_id)
               .order_by("-timestamp").first())
        if ult is not None:
            resumen = {
                "temperatura": ult.temperatura,
                "humedad_relativa": ult.humedad_relativa,
                "velocidad_viento": ult.velocidad_viento,
                "timestamp": timezone.localtime(ult.timestamp).isoformat(),
            }
    return {
        "device_id": consola.device_id,
        "nombre": consola.nombre,
        "en_linea": en_linea,
        "hace_seg": hace_seg,
        "ultimo_reporte": (consola.ultimo_reporte.isoformat()
                            if consola.ultimo_reporte else None),
        "ip_origen": consola.ip_origen,
        "software": consola.software,
        **resumen,
    }


@csrf_exempt
@require_GET
def ambient_consolas(request):
    """GET /api/v1/ambient/consolas/ — inventario de consolas en red."""
    consolas = ConsolaAmbient.objects.filter(activa=True)
    return JsonResponse({
        "ok": True,
        "umbral_offline_min": UMBRAL_OFFLINE_MIN,
        "n": consolas.count(),
        "consolas": [_resumen_consola(c) for c in consolas],
    })


def _uv_riesgo(uv):
    if uv is None:
        return None
    if uv < 3:
        return "LOW"
    if uv < 6:
        return "MODERATE"
    if uv < 8:
        return "HIGH"
    if uv < 11:
        return "VERY HIGH"
    return "EXTREME"


@csrf_exempt
@require_GET
def ambient_ultima(request):
    """GET /api/v1/ambient/ultima/ — solo estacion 99 (aislada)."""
    try:
        est = Estacion.objects.get(pk=AMBIENT_CODIGO)
    except Estacion.DoesNotExist:
        return JsonResponse({"ok": True, "disponible": False,
                             "mensaje": "aun no hay datos del Ambient"})
    ultima = (Lectura.objects.filter(estacion=est)
              .order_by("-timestamp").first())
    if ultima is None:
        return JsonResponse({"ok": True, "disponible": False,
                             "mensaje": "aun no hay datos del Ambient"})
    return JsonResponse({
        "ok": True,
        "disponible": True,
        "codigo": AMBIENT_CODIGO,
        "nombre": est.nombre,
        "timestamp": timezone.localtime(ultima.timestamp).isoformat(),
        # Edad (s) de la ultima lectura calculada en el SERVIDOR: el panel
        # refresca el badge EN LINEA/OFFLINE solo con el hace_seg de cada
        # respuesta, sin depender del reloj del visitante.
        "hace_seg": int((timezone.now() - ultima.timestamp).total_seconds()),
        "umbral_offline_min": UMBRAL_OFFLINE_MIN,
        "temperatura": ultima.temperatura,
        "humedad_relativa": ultima.humedad_relativa,
        "precipitacion": ultima.precipitacion,
        "presion_barometrica": ultima.presion_barometrica,
        "presion_absoluta": ultima.presion_absoluta,
        "velocidad_viento": ultima.velocidad_viento,
        "direccion_viento": ultima.direccion_viento,
        "racha_viento": ultima.racha_viento,
        "viento_promedio_10m": ultima.viento_promedio_10m,
        "radiacion_solar": ultima.radiacion_solar,
        "indice_uv": ultima.indice_uv,
        "temperatura_interior": ultima.temperatura_interior,
        "humedad_interior": ultima.humedad_interior,
        "lluvia_tasa": ultima.lluvia_tasa,
        "sensacion": _sensacion(ultima.temperatura, ultima.humedad_relativa,
                                ultima.velocidad_viento),
        "rocio": _rocio(ultima.temperatura, ultima.humedad_relativa),
        "rocio_in": _rocio(ultima.temperatura_interior,
                           ultima.humedad_interior),
        "sens_in": _sensacion(ultima.temperatura_interior,
                              ultima.humedad_interior, None),
        "uv_riesgo": _uv_riesgo(ultima.indice_uv),
        "lluvia_evento": ultima.lluvia_evento,
        "lluvia_hora": ultima.lluvia_hora,
        "lluvia_dia": ultima.lluvia_dia,
        "lluvia_semana": ultima.lluvia_semana,
        "lluvia_mes": ultima.lluvia_mes,
        "lluvia_anio": ultima.lluvia_anio,
    })


@csrf_exempt
@require_GET
def ambient_serie(request):
    """GET /api/v1/ambient/serie/ — ultimas 24 h solo estacion 99."""
    from datetime import timedelta
    try:
        est = Estacion.objects.get(pk=AMBIENT_CODIGO)
    except Estacion.DoesNotExist:
        return JsonResponse({"ok": True, "puntos": []})
    ultima = (Lectura.objects.filter(estacion=est)
              .order_by("-timestamp").first())
    if ultima is None:
        return JsonResponse({"ok": True, "puntos": []})
    hasta = ultima.timestamp
    desde = hasta - timedelta(hours=24)
    filas = (Lectura.objects
             .filter(estacion=est, timestamp__gte=desde,
                     timestamp__lte=hasta)
             .order_by("timestamp")
             .values("timestamp", "temperatura", "humedad_relativa",
                     "precipitacion", "presion_barometrica",
                     "presion_absoluta", "velocidad_viento",
                     "direccion_viento", "racha_viento",
                     "viento_promedio_10m", "radiacion_solar", "indice_uv",
                     "temperatura_interior", "humedad_interior",
                     "lluvia_tasa", "lluvia_evento", "lluvia_hora",
                     "lluvia_dia", "lluvia_semana", "lluvia_mes",
                     "lluvia_anio"))
    puntos = [{
        "t": timezone.localtime(f["timestamp"]).isoformat(),
        "temperatura": f["temperatura"],
        "humedad_relativa": f["humedad_relativa"],
        "precipitacion": f["precipitacion"],
        "presion_barometrica": f["presion_barometrica"],
        "presion_absoluta": f["presion_absoluta"],
        "velocidad_viento": f["velocidad_viento"],
        "direccion_viento": f["direccion_viento"],
        "racha_viento": f["racha_viento"],
        "viento_promedio_10m": f["viento_promedio_10m"],
        "radiacion_solar": f["radiacion_solar"],
        "indice_uv": f["indice_uv"],
        "temperatura_interior": f["temperatura_interior"],
        "humedad_interior": f["humedad_interior"],
        "lluvia_tasa": f["lluvia_tasa"],
        "lluvia_evento": f["lluvia_evento"],
        "lluvia_hora": f["lluvia_hora"],
        "lluvia_dia": f["lluvia_dia"],
        "lluvia_semana": f["lluvia_semana"],
        "lluvia_mes": f["lluvia_mes"],
        "lluvia_anio": f["lluvia_anio"],
    } for f in filas]
    return JsonResponse({
        "ok": True,
        "codigo": AMBIENT_CODIGO,
        "desde": timezone.localtime(desde).isoformat(),
        "hasta": timezone.localtime(hasta).isoformat(),
        "n": len(puntos),
        "puntos": puntos,
    })


@csrf_exempt
@require_GET
def ambient_pronostico(request):
    """GET /api/v1/ambient/pronostico/ — 7 dias + tira horaria Open-Meteo.

    Cache 30 min. Si no hay internet, responde ok:false y el panel
    muestra 'sin pronostico' sin romper los sensores locales.
    """
    from django.core.cache import caches
    try:
        from estaciones import pronostico as _p
    except Exception:
        return JsonResponse({"ok": False, "mensaje": "sin modulo"})
    clave = "ambient_pronostico_tarjetas_v2"
    try:
        got = caches["default"].get(clave)
        if got:
            return JsonResponse({"ok": True, "cache": True, **got})
    except Exception:
        pass
    try:
        import json as _j
        import urllib.request as _u
        url = (_p.URL_API + "?latitude=5.0687&longitude=-75.5174"
               "&daily=temperature_2m_max,temperature_2m_min,"
               "precipitation_probability_max,weathercode"
               "&hourly=temperature_2m,precipitation_probability,weathercode"
               "&forecast_days=7&timezone=America%2FBogota")
        req = _u.Request(url, headers={"User-Agent": "est-campus-unal/1.0"})
        with _u.urlopen(req, timeout=_p.TIMEOUT_S) as r:
            raw = _j.load(r)
        proble = {0: "S", 1: "PS", 2: "PN", 3: "N", 45: "NB", 48: "NB",
                  51: "LL", 53: "LL", 55: "LL", 61: "LL", 63: "LL",
                  65: "LL", 80: "LL", 81: "LL", 82: "T", 95: "T",
                  96: "T", 99: "T"}.get
        dias, d = [], raw.get("daily", {})
        # Nombre completo en espanol de cada dia de la semana.
        por_dia = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes",
                   "Sábado", "Domingo")
        for i, f in enumerate(d.get("time", [])[:7]):
            import datetime as _dt
            wd = _dt.date.fromisoformat(f).weekday()
            dias.append({
                "dia": por_dia[wd],
                "tmax": d.get("temperature_2m_max", [None])[i],
                "tmin": d.get("temperature_2m_min", [None])[i],
                "prob": d.get("precipitation_probability_max", [None])[i],
                "icono": proble((d.get("weathercode") or [None])[i], "PN"),
            })
        horas, h = [], raw.get("hourly", {})
        for i in range(0, min(24, len(h.get("time", []))), 2)[:8]:
            horas.append({
                "hora": (h["time"][i][11:13]),
                "temp": h.get("temperature_2m", [None])[i],
                "prob": h.get("precipitation_probability", [None])[i],
                "icono": proble((h.get("weathercode") or [None])[i], "PN"),
            })
        dato = {"dias": dias, "horas": horas,
                "tmax_hoy": dias[0]["tmax"] if dias else None,
                "tmin_hoy": dias[0]["tmin"] if dias else None}
        try:
            caches["default"].set(clave, dato, 1800)
        except Exception:
            pass
        return JsonResponse({"ok": True, "cache": False, **dato})
    except Exception as e:
        return JsonResponse({"ok": False, "mensaje": str(e)[:120]})
