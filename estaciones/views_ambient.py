# -*- coding: utf-8 -*-
"""Vista del panel Ambient (aislado del dashboard principal)."""
import math
from datetime import datetime, timedelta, timezone as dt_utc

from django.shortcuts import render
from django.utils import timezone

from estaciones.api.ambient_vistas import UMBRAL_OFFLINE_MIN, estado_red, estado_texto, consola_de_estacion
from estaciones.models import ConsolaAmbient, Estacion, Lectura
from estaciones.api.ambient import AMBIENT_CODIGO


_RUMBOS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)


def _rumbo(grados):
    if grados is None:
        return None
    try:
        return _RUMBOS[int((float(grados) % 360.0) / 22.5 + 0.5) % 16]
    except (TypeError, ValueError):
        return None


def _punto_rocio(t, hr):
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


def _consola(ultima, est):
    """Arma el dict estilo consola Ambient a partir de la ultima lectura."""
    if ultima is None:
        return None
    temp = ultima.temperatura
    hr = ultima.humedad_relativa
    vel = ultima.velocidad_viento
    d = {
        "codigo": AMBIENT_CODIGO,
        "nombre": est.nombre if est else "Ambient experimentoUN",
        "timestamp": timezone.localtime(ultima.timestamp),
        "temperatura": temp,
        "humedad": hr,
        "sensacion": _sensacion(temp, hr, vel),
        "rocio": _punto_rocio(temp, hr),
        "temp_interior": ultima.temperatura_interior,
        "hum_interior": ultima.humedad_interior,
        "viento": vel,
        "viento_kmh": round(vel * 3.6, 1) if vel is not None else None,
        "direccion": ultima.direccion_viento,
        "rumbo": _rumbo(ultima.direccion_viento),
        "racha": ultima.racha_viento,
        "racha_kmh": (round(ultima.racha_viento * 3.6, 1)
                       if ultima.racha_viento is not None else None),
        "prom10m": ultima.viento_promedio_10m,
        "prom10_kmh": (round(ultima.viento_promedio_10m * 3.6, 1)
                       if ultima.viento_promedio_10m is not None else None),
        "radiacion": ultima.radiacion_solar,
        "uv": ultima.indice_uv,
        "presion": ultima.presion_barometrica,
        "presion_abs": ultima.presion_absoluta,
        "lluvia_tasa": ultima.lluvia_tasa,
        "lluvia_evento": ultima.lluvia_evento,
        "lluvia_hora": ultima.lluvia_hora,
        "lluvia_dia": ultima.lluvia_dia,
        "lluvia_semana": ultima.lluvia_semana,
        "lluvia_mes": ultima.lluvia_mes,
        "lluvia_anio": ultima.lluvia_anio,
    }
    return d


def ambient(request):
    """Panel /ambient/.

    Sin parametro: grilla de consolas en red (LUNA y las que se conecten).
    Con ?consola=LUNA: detalle en vivo de esa consola.
    """
    device_id = (request.GET.get("consola") or "").strip()
    if not device_id:
        return _red(request)
    try:
        consola_reg = ConsolaAmbient.objects.get(device_id=device_id)
    except ConsolaAmbient.DoesNotExist:
        return _red(request)
    est = consola_reg.estacion
    if est is None:
        try:
            est = Estacion.objects.get(pk=AMBIENT_CODIGO)
        except Estacion.DoesNotExist:
            est = None
    return _detalle(request, est, device_id)


def _red(request):
    """Grilla de dispositivos: en linea / offline."""
    ahora = timezone.now()
    fichas = []
    for c in ConsolaAmbient.objects.filter(activa=True):
        hace_seg = None
        en_linea = False
        if c.ultimo_reporte is not None:
            hace_seg = int((ahora - c.ultimo_reporte).total_seconds())
            en_linea = hace_seg <= UMBRAL_OFFLINE_MIN * 60
        ult_temp = ult_hr = ult_viento = None
        if c.estacion_id is not None:
            ult = (Lectura.objects.filter(estacion_id=c.estacion_id)
                   .order_by("-timestamp").first())
            if ult is not None:
                ult_temp, ult_hr = ult.temperatura, ult.humedad_relativa
                ult_viento = (round(ult.velocidad_viento * 3.6, 1)
                              if ult.velocidad_viento is not None else None)
        fichas.append({
            "device_id": c.device_id,
            "nombre": c.nombre,
            "en_linea": en_linea,
            "hace_seg": hace_seg,
            "ultimo_reporte": (timezone.localtime(c.ultimo_reporte)
                                if c.ultimo_reporte else None),
            "ip_origen": c.ip_origen,
            "software": c.software,
            "temperatura": ult_temp,
            "humedad": ult_hr,
            "viento_kmh": ult_viento,
        })
    fichas.sort(key=lambda f: (not f["en_linea"],
                               f["hace_seg"] if f["hace_seg"] is not None else 10 ** 9))
    return render(request, "ambient_red.html", {
        "fichas": fichas,
        "umbral_min": UMBRAL_OFFLINE_MIN,
    })


def _amanecer_atadecer(lat=5.0687, lon=-75.5174):
    """Amanecer/atardecer aprox (algoritmo NOAA, sin dependencias).

    Manizales por defecto. Devuelve datetimes America/Bogota de hoy.
    """
    try:
        from zoneinfo import ZoneInfo
        bog = ZoneInfo("America/Bogota")
    except Exception:
        bog = dt_utc.utc
    hoy = datetime.now(bog).date()
    n = hoy.timetuple().tm_yday
    lng_h = lon / 15.0
    import math as _m
    lat_r = _m.radians(lat)

    def evento(salida):
        t = n + ((6 if salida else 18) - lng_h) / 24.0
        m = (0.9856 * t) - 3.289
        l = (m + 1.916 * _m.sin(_m.radians(m))
             + 0.020 * _m.sin(_m.radians(2 * m)) + 282.634) % 360
        ra = _m.degrees(_m.atan(0.91764 * _m.tan(_m.radians(l))))
        ra = (ra / 15.0 + (l // 90) * 6 - (ra // 90) * 6) % 24
        sin_d = 0.39782 * _m.sin(_m.radians(l))
        cos_d = _m.cos(_m.asin(sin_d))
        zen = _m.radians(90.833)
        cos_h = ((_m.cos(zen) - sin_d * _m.sin(lat_r))
                 / (cos_d * _m.cos(lat_r)))
        cos_h = max(-1.0, min(1.0, cos_h))
        h = _m.degrees(_m.acos(cos_h))
        h = (360 - h) / 15.0 if salida else h / 15.0
        t = h + ra - (0.06571 * t) - 6.622
        utc_h = (t - lng_h) % 24
        base = datetime(hoy.year, hoy.month, hoy.day, tzinfo=dt_utc.utc)
        return (base + timedelta(hours=utc_h)).astimezone(bog)

    return evento(True), evento(False)


def _escena_inicial(consola):
    """Escena/momento iniciales (el JS la refina cada 15 s con viva())."""
    if consola is None:
        return "standby", "dia"
    sens = consola.get("sensacion", consola.get("temperatura"))
    hr = consola.get("humedad")
    rad = consola.get("radiacion")
    tasa = consola.get("lluvia_tasa") or 0
    hora = consola.get("lluvia_hora") or 0
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo("America/Bogota")).hour
    except Exception:
        h = 12
    noche = h < 6 or h >= 18
    mom = "noche" if noche else "dia"
    if tasa and tasa > 0:
        return "lluvia", mom
    if (hora and hora > 0) or (hr is not None and hr >= 88):
        return "porllover", mom
    if sens is not None and sens <= 10:
        return "frio", mom
    if sens is not None and sens >= 27:
        return "calor", mom
    if not noche and rad is not None:
        if rad < 150:
            return "nublado", mom
        if rad < 350 or (hr is not None and hr > 70):
            return "nublado", mom
        return "despejado", mom
    return "despejado", mom


def _ayer(est, ultima):
    """Temp/HR de ayer a la misma hora (para 'From Yesterday')."""
    if est is None or ultima is None:
        return None, None
    objetivo = ultima.timestamp - timedelta(hours=24)
    fila = (Lectura.objects.filter(estacion=est, timestamp__lte=objetivo)
            .order_by("-timestamp")
            .values("temperatura", "humedad_relativa").first())
    if not fila:
        return None, None
    return fila.get("temperatura"), fila.get("humedad_relativa")


# Nombre legible y unidad de cada tarjeta del carrusel de estadisticas.
_NOMBRES_STATS = {
    "temperatura": ("Temperatura", "°C"),
    "humedad_relativa": ("Humedad relativa", "%"),
    "presion_barometrica": ("Presión barométrica", "hPa"),
    "velocidad_viento": ("Velocidad del viento", "m/s"),
    "radiacion_solar": ("Radiación solar", "W/m²"),
    "precipitacion": ("Precipitación", ""),
    "direccion_viento": ("Dirección del viento", ""),
}


def _precipitacion_dia(filas):
    """Total del día (mm) y máxima tasa (mm/h) de la lluvia.

    La consola Ambient reporta los acumulados propios (lluvia_dia y
    lluvia_tasa); el campo 'precipitacion' por lectura solo llega si la
    consola manda hourlyrainin, asi que se usa como respaldo.
    """
    acums = [f.lluvia_dia for f in filas if f.lluvia_dia is not None]
    tasas = [f.lluvia_tasa for f in filas if f.lluvia_tasa is not None]
    brutas = [f.precipitacion for f in filas if f.precipitacion is not None]
    total = max(acums) if acums else (sum(brutas) if brutas else 0.0)
    max_rate = max(tasas) if tasas else (max(brutas) if brutas else 0.0)
    return {"total": round(total, 1), "max_rate": round(max_rate, 1),
            "avg": None}


def _detalle(request, est, device_id):
    """Detalle en vivo de una consola (el panel anterior)."""
    ultima = None
    hace = None
    en_linea = False
    recientes = []
    consola = None
    tmax = tmin = None
    pico_rachas = None
    pico_rad = None
    ayer_t = ayer_h = None
    consola_db = consola_de_estacion(est.pk) if est is not None else None
    if est is not None:
        ultima = (Lectura.objects.filter(estacion=est)
                  .order_by("-timestamp").first())
        if ultima is not None:
            delta = timezone.now() - ultima.timestamp
            hace = delta
            consola = _consola(ultima, est)
            # Max/min del dia + racha pico del dia (para la consola).
            inicio_dia = timezone.localtime(ultima.timestamp).replace(
                hour=0, minute=0, second=0, microsecond=0)
            inicio_utc = inicio_dia.astimezone(dt_utc.utc)
            del_dia = Lectura.objects.filter(
                estacion=est, timestamp__gte=inicio_utc,
                timestamp__lte=ultima.timestamp)
            from django.db.models import Max, Min
            agg = del_dia.aggregate(tmax=Max("temperatura"),
                                    tmin=Min("temperatura"),
                                    racha=Max("racha_viento"),
                                    radmax=Max("radiacion_solar"))
            tmax, tmin, pico_rachas = agg["tmax"], agg["tmin"], agg["racha"]
            pico_rad = agg["radmax"]
            # Estadísticas del día para el carrusel de sensores.
            filas_dia = list(del_dia)
            from collections import Counter

            def _stat(attr):
                vals = [getattr(f, attr) for f in filas_dia if getattr(f, attr) is not None]
                if not vals:
                    return {"max": None, "min": None, "avg": None}
                return {"max": max(vals), "min": min(vals),
                        "avg": round(sum(vals) / len(vals), 1)}

            stats = {
                "temperatura": _stat("temperatura"),
                "humedad_relativa": _stat("humedad_relativa"),
                "presion_barometrica": _stat("presion_barometrica"),
                "velocidad_viento": _stat("velocidad_viento"),
                "radiacion_solar": _stat("radiacion_solar"),
                "precipitacion": _precipitacion_dia(filas_dia),
                "direccion_viento": {"dominante": None},
            }
            dirs = [f.direccion_viento for f in filas_dia if f.direccion_viento is not None]
            if dirs:
                stats["direccion_viento"]["dominante"] = Counter(dirs).most_common(1)[0][0]
            # Nombre legible + unidad para las tarjetas del carrusel.
            for _k, _s in stats.items():
                _s["nom"], _s["unidad"] = _NOMBRES_STATS.get(
                    _k, (_k.replace("_", " ").title(), ""))
            # Series del día para las graficas (grid grande + sparks del
            # carrusel). 'precipitacion' usa la tasa de lluvia como respaldo
            # porque la consola Ambient no manda hourlyrainin.
            attrs_series = ["temperatura", "humedad_relativa",
                            "presion_barometrica", "velocidad_viento",
                            "racha_viento", "radiacion_solar", "indice_uv",
                            "lluvia_tasa", "lluvia_dia", "direccion_viento",
                            "precipitacion"]
            series = {a: [] for a in attrs_series}
            for f in filas_dia:
                ts = timezone.localtime(f.timestamp).isoformat()
                for a in attrs_series:
                    v = getattr(f, a)
                    if a == "precipitacion" and v is None:
                        v = f.lluvia_tasa
                    series[a].append([ts, v])
        recientes = list(
            Lectura.objects.filter(estacion=est)
            .order_by("-timestamp")
            .values("timestamp", "temperatura", "humedad_relativa",
                    "precipitacion", "presion_barometrica",
                    "velocidad_viento", "direccion_viento",
                    "radiacion_solar", "lluvia_dia")[:20]
        )
        for r in recientes:
            r["timestamp"] = timezone.localtime(r["timestamp"])
            # La consola Ambient casi nunca manda 'precipitacion' (solo si
            # llega hourlyrainin): mostrar el acumulado del dia como respaldo
            # para no pintar una columna de '—'.
            if r["precipitacion"] is None:
                r["precipitacion"] = r.pop("lluvia_dia")
            else:
                r.pop("lluvia_dia", None)
    estado_txt_val = "SIN DATOS RECIENTES"
    if ultima is not None:
        en_linea, motivo, _ = estado_red(
            consola_db, edad_lectura_seg=int(hace.total_seconds()))
        estado_txt_val = estado_texto(motivo)
    else:
        en_linea = False
    if ultima is not None:
        ultima_hora = timezone.localtime(ultima.timestamp)
    else:
        ultima_hora = None
    ayer_t, ayer_h = _ayer(est, ultima)
    if consola is not None:
        consola["tmax_hoy"] = tmax
        consola["tmin_hoy"] = tmin
        consola["racha_pico_hoy"] = pico_rachas
        consola["racha_pico_kmh"] = (round(pico_rachas * 3.6, 1)
                                     if pico_rachas is not None else None)
        consola["pico_rad_hoy"] = pico_rad
        consola["ayer_temp"] = ayer_t
        consola["ayer_hum"] = ayer_h
        # Rocio/sensacion interior con las mismas formulas del exterior.
        consola["rocio_in"] = _punto_rocio(consola.get("temp_interior"),
                                           consola.get("hum_interior"))
        consola["sens_in"] = _sensacion(consola.get("temp_interior"),
                                        consola.get("hum_interior"), None)
        # Etiqueta UV estilo Ecowitt.
        try:
            uv = consola.get("uv")
            consola["uv_riesgo"] = ("LOW" if uv is not None and uv < 3
                                    else "MODERATE" if uv is not None and uv < 6
                                    else "HIGH" if uv is not None and uv < 8
                                    else "VERY HIGH" if uv is not None and uv < 11
                                    else "EXTREME" if uv is not None else None)
        except TypeError:
            consola["uv_riesgo"] = None
    try:
        from estaciones.ml.predictor import predecir
        prediccion = predecir(device_id, horizonte=6)
    except Exception:
        prediccion = {"ok": False, "motivo": "error"}

    ctx = {
        "estacion": est,
        "stats": stats if ultima is not None else None,
        "series": series if ultima is not None else {},
        "codigo": AMBIENT_CODIGO,
        "device_id": device_id,
        "ultima": ultima,
        "consola": consola,
        "ultima_hora": ultima_hora,
        "hace_seg": int(hace.total_seconds()) if hace is not None else None,
        "en_linea": en_linea,
        "estado_txt": estado_txt_val,
        "recientes": recientes,
        "escena": _escena_inicial(consola)[0] if en_linea else "standby",
        "momento": _escena_inicial(consola)[1],
        "amanecer": _amanecer_atadecer()[0],
        "atardecer": _amanecer_atadecer()[1],
        "prediccion": prediccion,
    }
    return render(request, "ambient_consola.html", ctx)
