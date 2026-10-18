# -*- coding: utf-8 -*-
"""
Pronostico y visibilidad via Open-Meteo.

Las estaciones NO miden visibilidad ni emiten pronostico: estos datos vienen
del modelo de Open-Meteo (API libre, sin llave) para las coordenadas de cada
estacion. Por eso las tarjetas del dashboard los etiquetan como "(Open-Meteo)".

El resultado se cachea 10 minutos: el pronostico no cambia tan rapido y asi
el refresco de 1 min del dashboard no golpea la API externa en vano.
"""
import json
import urllib.request

URL_API = "https://api.open-meteo.com/v1/forecast"
TTL_CACHE_S = 600          # 10 minutos
TIMEOUT_S = 8

# Codigos WMO (campo weather_code) -> (texto en espanol, emoji).
WMO = {
    0: ("Despejado", "☀️"),
    1: ("Mayormente despejado", "🌤️"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"),
    45: ("Niebla", "🌫️"),
    48: ("Niebla escarchada", "🌫️"),
    51: ("Llovizna ligera", "🌦️"),
    53: ("Llovizna", "🌦️"),
    55: ("Llovizna intensa", "🌧️"),
    56: ("Llovizna helada ligera", "🌧️"),
    57: ("Llovizna helada", "🌧️"),
    61: ("Lluvia ligera", "🌦️"),
    63: ("Lluvia moderada", "🌧️"),
    65: ("Lluvia fuerte", "🌧️"),
    66: ("Lluvia helada ligera", "🌧️"),
    67: ("Lluvia helada fuerte", "🌧️"),
    71: ("Nieve ligera", "🌨️"),
    73: ("Nieve", "🌨️"),
    75: ("Nieve fuerte", "❄️"),
    77: ("Granizo menudo", "🌨️"),
    80: ("Chubascos ligeros", "🌦️"),
    81: ("Chubascos", "🌧️"),
    82: ("Chubascos violentos", "⛈️"),
    85: ("Chubascos de nieve", "🌨️"),
    86: ("Chubascos de nieve fuertes", "❄️"),
    95: ("Tormenta electrica", "⛈️"),
    96: ("Tormenta con granizo", "⛈️"),
    99: ("Tormenta con granizo fuerte", "⛈️"),
}


def _wmo(codigo, de_noche=False):
    """Texto y emoji del codigo WMO; de noche el cielo despejado es luna."""
    texto, emoji = WMO.get(codigo, ("Sin dato", "❔"))
    if de_noche and codigo in (0, 1):
        emoji = "🌙"
    return texto, emoji


def _vis_categoria(metros):
    """Categoria cualitativa de la visibilidad (m)."""
    if metros is None:
        return None
    km = metros / 1000.0
    if km >= 10:
        return "Excelente"
    if km >= 4:
        return "Buena"
    if km >= 1:
        return "Moderada"
    if km >= 0.2:
        return "Baja"
    return "Muy baja (niebla densa)"


def _en(lista, i):
    """lista[i] con tolerancia a listas cortas o ausentes."""
    try:
        return lista[i]
    except (IndexError, TypeError):
        return None


def consultar(lat, lon):
    """
    Consulta Open-Meteo y devuelve el dict listo para el JsonResponse.

    Lanza excepcion si la API externa falla: quien llama (la vista) decide
    si responde 502 o sirve la cache vieja.
    """
    params = (
        f"latitude={lat}&longitude={lon}"
        "&current=weather_code,is_day,visibility"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&forecast_days=2&timezone=America%2FBogota"
    )
    req = urllib.request.Request(
        f"{URL_API}?{params}", headers={"User-Agent": "est-campus-unal/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        raw = json.load(r)

    act = raw.get("current", {})
    vis_m = act.get("visibility")
    texto, emoji = _wmo(act.get("weather_code"), de_noche=act.get("is_day") == 0)

    # Proximas horas: desde la hora actual, una muestra cada 3 h (4 en total).
    h = raw.get("hourly", {})
    tiempos = h.get("time") or []
    ahora_txt = (act.get("time") or "")[:13]      # "2026-10-12T11"
    inicio = next((i for i, t in enumerate(tiempos)
                   if t[:13] >= ahora_txt), 0)
    horas = []
    for i in range(inicio, min(inicio + 12, len(tiempos)), 3):
        t_txt, t_emoji = _wmo(_en(h.get("weather_code"), i))
        temp = _en(h.get("temperature_2m"), i)
        prob = _en(h.get("precipitation_probability"), i)
        horas.append({
            "hora": tiempos[i][11:16],            # "14:00"
            "texto": t_txt,
            "emoji": t_emoji,
            "temperatura": round(temp, 1) if temp is not None else None,
            "prob_lluvia": int(round(prob)) if prob is not None else None,
        })

    return {
        "actual": {
            "texto": texto,
            "emoji": emoji,
            "visibilidad_m": vis_m,
            "visibilidad_km": round(vis_m / 1000.0, 2) if vis_m is not None else None,
            "visibilidad_categoria": _vis_categoria(vis_m),
        },
        "horas": horas,
    }
