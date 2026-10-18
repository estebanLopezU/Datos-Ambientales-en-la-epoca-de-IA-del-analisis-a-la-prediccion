# -*- coding: utf-8 -*-
"""
Receptor para consolas Ambient Weather / Ecowitt (protocolo Wunderground).

La consola NO habla JSON: hace GET a
  /weatherstation/updateweatherstation.php?tempf=..&humidity=..&...

Este modulo traduce esas unidades imperiales a las metricas del proyecto
y guarda como Lectura de la estacion AMBIENT_CODIGO (99), totalmente
aparte de La Nubia (24) y Palogrande (29).

Responde "success" porque la consola lo exige; sin eso reintenta.
"""
from datetime import datetime, timezone as dt_utc

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from estaciones.models import Estacion, Lectura
from estaciones.api.endpoints import RANGOS

# Estacion logica del experimento: no toca 24 ni 29.
AMBIENT_CODIGO = 99
AMBIENT_NOMBRE = "Ambient experimentoUN"
AMBIENT_CAMPUS = "experimentoUN (red local)"

_MPH_A_MS = 0.44704
_IN_A_MM = 25.4
_INHG_A_HPA = 33.8639


def _num(valor):
    """Float tolerante (acepta coma decimal). None si no es numero.

    La consola manda -9999 como 'sin sensor': se trata como ausente.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return None if float(valor) <= -9990.0 else float(valor)
    try:
        n = float(str(valor).strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None
    return None if n <= -9990.0 else n


def _en_rango(variable, valor):
    """Valida contra los mismos RANGOS del endpoint principal."""
    if valor is None:
        return None
    minimo, maximo = RANGOS[variable]
    if not (minimo <= valor <= maximo):
        return None
    return valor


def traducir_ambient(params):
    """Traduce query params Ambient/Ecowitt a campos de Lectura."""
    advertencias = []
    campos = {}

    # La consola manda algunas claves en mayusculas (UV, ID, PASSWORD...):
    # se normaliza todo a minusculas para no perderlas.
    params = {str(k).lower(): v for k, v in params.items()}

    tempf = _num(params.get("tempf"))
    if tempf is not None:
        temp_c = _en_rango("temperatura", (tempf - 32.0) * 5.0 / 9.0)
        if temp_c is None:
            advertencias.append(f"temperatura fuera de rango ({tempf} F)")
        else:
            campos["temperatura"] = round(temp_c, 1)

    hum = _num(params.get("humidity"))
    if hum is not None:
        h = _en_rango("humedad_relativa", hum)
        if h is None:
            advertencias.append(f"humedad fuera de rango ({hum})")
        else:
            campos["humedad_relativa"] = h

    baro = _num(params.get("baromin"))
    if baro is None:
        # Algunas consolas mandan presion absoluta en otro campo.
        baro = _num(params.get("baromabsin"))
    if baro is not None:
        # El RANGOS del proyecto (400-900 hPa) es para presion de estacion
        # en Manizales (~600 hPa); el Ambient manda QNH (~1013 hPa). Se
        # acepta el rango de consola 26-32 inHg y se guarda tal cual.
        if 26.0 <= baro <= 32.0:
            campos["presion_barometrica"] = round(baro * _INHG_A_HPA, 1)
        else:
            advertencias.append(f"presion fuera de rango ({baro} inHg)")

    viento = _num(params.get("windspeedmph"))
    if viento is not None:
        vel = _en_rango("velocidad_viento", viento * _MPH_A_MS)
        if vel is None:
            advertencias.append(f"viento fuera de rango ({viento} mph)")
        else:
            campos["velocidad_viento"] = round(vel, 1)

    direccion = _num(params.get("winddir"))
    if direccion is not None:
        d = _en_rango("direccion_viento", direccion % 360.0)
        if d is None:
            advertencias.append(f"direccion fuera de rango ({direccion})")
        else:
            campos["direccion_viento"] = d

    sol = _num(params.get("solarradiation"))
    if sol is not None:
        s = _en_rango("radiacion_solar", sol)
        if s is None:
            advertencias.append(f"radiacion fuera de rango ({sol})")
        else:
            campos["radiacion_solar"] = s

    lluvia_h = _num(params.get("hourlyrainin"))
    if lluvia_h is not None:
        ll = _en_rango("precipitacion", lluvia_h * _IN_A_MM)
        if ll is None:
            advertencias.append(f"lluvia fuera de rango ({lluvia_h} in)")
        else:
            campos["precipitacion"] = round(ll, 1)
            campos["lluvia_hora"] = round(ll, 1)

    def _lluvia(clave_in, destino, etiqueta):
        v = _num(params.get(clave_in))
        if v is not None:
            mm = round(v * _IN_A_MM, 1)
            if 0.0 <= mm <= 5000.0:
                campos[destino] = mm
            else:
                advertencias.append(f"{etiqueta} fuera de rango ({v} in)")

    _lluvia("dailyrainin", "lluvia_dia", "lluvia diaria")
    _lluvia("weeklyrainin", "lluvia_semana", "lluvia semanal")
    _lluvia("monthlyrainin", "lluvia_mes", "lluvia mensual")
    _lluvia("yearlyrainin", "lluvia_anio", "lluvia anual")
    _lluvia("eventrainin", "lluvia_evento", "lluvia evento")
    _lluvia("rainratein", "lluvia_tasa", "tasa de lluvia")

    # Sensores interiores + viento extra + UV (todo opcional).
    # Sensores interiores + viento extra + UV (todo opcional).
    t_in = _num(params.get("tempinf"))
    if t_in is not None:
        c = (t_in - 32.0) * 5.0 / 9.0
        if -30.0 <= c <= 60.0:
            campos["temperatura_interior"] = round(c, 1)
        else:
            advertencias.append(f"temp interior fuera de rango ({t_in} F)")

    h_in = _num(params.get("humidityin"))
    if h_in is not None:
        if 0.0 <= h_in <= 100.0:
            campos["humedad_interior"] = h_in
        else:
            advertencias.append(f"humedad interior fuera de rango ({h_in})")

    for clave_in, destino, etiqueta in (
        ("windgustmph", "racha_viento", "racha"),
        ("windspdmph_avg10m", "viento_promedio_10m", "viento 10min"),
        ("windgustmph_10m", "racha_viento", "racha 10min"),
    ):
        v = _num(params.get(clave_in))
        if v is not None and destino not in campos:
            ms = v * _MPH_A_MS
            if 0.0 <= ms <= 60.0:
                campos[destino] = round(ms, 1)
            else:
                advertencias.append(f"{etiqueta} fuera de rango ({v} mph)")

    uv = _num(params.get("uv"))
    if uv is not None:
        if 0.0 <= uv <= 20.0:
            campos["indice_uv"] = uv
        else:
            advertencias.append(f"uv fuera de rango ({uv})")

    abs_in = _num(params.get("baromabsin"))
    if abs_in is not None and 26.0 <= abs_in <= 32.0:
        campos["presion_absoluta"] = round(abs_in * _INHG_A_HPA, 1)

    ts = None
    dateutc = (params.get("dateutc") or "").strip()
    if dateutc:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                ingenuo = datetime.strptime(dateutc, fmt)
                ts = timezone.make_aware(ingenuo, dt_utc.utc)
                break
            except ValueError:
                continue
        if ts is None:
            advertencias.append(f"dateutc no reconocido ({dateutc})")
    if ts is None:
        ts = timezone.now()
    campos["timestamp"] = ts
    return campos, advertencias


def dispositivo_desde_params(params):
    """ID de la consola (parametro ID/PASSKEY/MAC). 'DESCONOCIDA' si no hay."""
    bajas = {str(k).lower(): v for k, v in params.items()}
    for clave in ("id", "passkey", "mac", "stationtype"):
        valor = (bajas.get(clave) or "").strip()
        if valor and valor != "x":
            return valor[:64]
    return "DESCONOCIDA"


def estacion_ambient():
    """Obtiene o crea la estacion logica 99 (sin tocar 24/29)."""
    est, _ = Estacion.objects.get_or_create(
        codigo=AMBIENT_CODIGO,
        defaults={"nombre": AMBIENT_NOMBRE, "campus": AMBIENT_CAMPUS,
                  "activa": True},
    )
    return est
