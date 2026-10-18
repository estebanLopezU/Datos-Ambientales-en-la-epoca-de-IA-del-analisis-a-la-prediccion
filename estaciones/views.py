# -*- coding: utf-8 -*-
"""
Vistas del dashboard y de la API de consulta.

El dashboard necesita dos cosas:
  1. el estado actual de cada estacion (ultima lectura)
  2. una serie temporal de las ultimas 24 h para las graficas

La serie se agrega antes de enviarse: una ventana de 24 h a 5 min son 288 puntos
por estacion (y 5.400 si el demo va a 16 s). En crudo eso hace que el navegador
se ponga lento, asi que se agrupa por minutos configurables.
"""
import math
from datetime import timedelta

from django.db.models import (Avg, CharField, Count, Max, Min, Sum)
from django.db.models.expressions import RawSQL
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Estacion, Lectura
from . import pronostico
from django.core.cache import cache

VENTANA_HORAS = 24

# Estaciones del dashboard principal. La 99 (Ambient experimentoUN) es un
# modulo aparte: no aparece en tarjetas, ultima, serie ni historial.
ESTACIONES_PRINCIPALES = (24, 29)

# Variables que se grafican y su etiqueta para la leyenda.
SERIES = {
    "temperatura": "Temperatura (C)",
    "humedad_relativa": "Humedad (%)",
    "precipitacion": "Precipitacion (mm)",
    "presion_barometrica": "Presion (hPa)",
    "velocidad_viento": "Viento (m/s)",
    "radiacion_solar": "Radiacion solar (W/m2)",
}


def _rango_24h():
    """Devuelve (desde, hasta) en la zona horaria del proyecto."""
    ahora = timezone.localtime()
    return ahora - timedelta(hours=VENTANA_HORAS), ahora


def _minutos_agrupacion(horas=VENTANA_HORAS, objetivo_puntos=150):
    """
    Minutos por punto para no saturar la grafica.

    Con datos cada 5 min y 24 h (288 puntos) el paso es de 10 min: la grafica
    queda en unos 144 puntos, fluida en cualquier navegador.
    Con el demo a 16 s (5.400 puntos) tambien se comprime a esa escala.
    """
    return max(1, int(round(horas * 60 / objetivo_puntos)))


# ---------- metricas derivadas (sensacion, rocio, tendencias) ----------

_UM_BEAUFORT = (0.5, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7)
_BEAUFORT_TXT = (
    "Calma", "Brisa inapreciable", "Brisa ligera", "Brisa suave",
    "Brisa moderada", "Brisa fresca", "Brisa fuerte", "Viento fuerte",
    "Viento muy fuerte", "Viento temporal", "Temporal fuerte", "Huracado",
)


def _punto_rocio(t, hr):
    """Punto de rocio (C) con la aproximacion de Magnus."""
    if t is None or hr is None or not (0 < hr <= 100):
        return None
    gamma = math.log(hr / 100.0) + (17.62 * t) / (243.12 + t)
    return round(243.12 * gamma / (17.62 - gamma), 1)


def _sensacion(t, hr, v):
    """
    Temperatura aparente en C:
      - T >= 27 C: indice de calor de Rothfusz (NWS).
      - T <= 10 C con viento >= 4,8 km/h: enfriamiento por el viento (NWS).
      - resto: la temperatura del aire (no hay sensacion relevante).
    """
    if t is None:
        return None
    if t >= 27 and hr is not None:
        tf, r = t * 9 / 5 + 32, hr
        hi = (-42.379 + 2.04901523 * tf + 10.14333127 * r
              - 0.22475541 * tf * r - 0.00683783 * tf ** 2
              - 0.05481717 * r ** 2 + 0.00122874 * tf ** 2 * r
              + 0.00085282 * tf * r ** 2 - 0.00000199 * tf ** 2 * r ** 2)
        # Si el indice de calor baja de la temperatura del aire, manda el aire.
        return round(max((hi - 32) * 5 / 9, t), 1)
    if t <= 10 and v is not None and v * 3.6 >= 4.8:
        vf, tf = v * 2.236936, t * 9 / 5 + 32       # m/s -> mph
        wc = (35.74 + 0.6215 * tf - 35.75 * vf ** 0.16
              + 0.4275 * tf * vf ** 0.16)
        return round(min((wc - 32) * 5 / 9, t), 1)
    return round(t, 1)


def _beaufort(v):
    """Fuerza de Beaufort (0-12) y su descripcion en espanol."""
    if v is None:
        return None, None
    fuerza = len(_UM_BEAUFORT)
    for i, umbral in enumerate(_UM_BEAUFORT):
        if v < umbral:
            fuerza = i
            break
    return fuerza, _BEAUFORT_TXT[fuerza]


def _uv_estimado(rad):
    """
    Indice UV aproximado a partir de la radiacion global (W/m2).

    La red NO tiene sensor UV: UVI ~ radiacion/95 es la regla practica a
    mediodia despejado (1000 W/m2 -> UVI 10); por eso la tarjeta lo
    etiqueta como "estimado".
    """
    if rad is None:
        return None
    return max(0, min(11, int(round(rad / 95.0))))


def _uv_categoria(uvi):
    if uvi is None:
        return None
    if uvi <= 2:
        return "Bajo"
    if uvi <= 5:
        return "Moderado"
    if uvi <= 7:
        return "Alto"
    if uvi <= 10:
        return "Muy alto"
    return "Extremo"


def _hace_txt(ts):
    """Texto en espanol de 'hace cuanto' respecto de ahora (para 'Registro')."""
    seg = max(0.0, (timezone.now() - ts).total_seconds())
    if seg < 90:
        return "hace un momento"
    minutos = seg / 60.0
    if minutos < 60:
        return f"hace {int(round(minutos))} min"
    horas = minutos / 60.0
    if horas < 24:
        return f"hace {int(round(horas))} h"
    dias = horas / 24.0
    if dias < 30:
        n = int(round(dias))
        return f"hace {n} dia" + ("s" if n != 1 else "")
    meses = dias / 30.4
    if meses < 12:
        n = int(round(meses))
        return f"hace {n} mes" + ("es" if n != 1 else "")
    n = max(1, int(dias / 365))
    return f"hace {n} anio" + ("s" if n != 1 else "")


def _derivados(est, ultima):
    """
    Metricas derivadas de la ultima lectura para las tarjetas.

    Todas las ventanas se anclan al timestamp de la ultima lectura (no a
    now()), igual que el resto del dashboard: asi funcionan igual con los
    historicos que con datos en vivo.
    """
    ts = ultima.timestamp
    inicio_dia = timezone.localtime(ts).replace(
        hour=0, minute=0, second=0, microsecond=0)
    t, hr, v = ultima.temperatura, ultima.humedad_relativa, ultima.velocidad_viento

    uvi = _uv_estimado(ultima.radiacion_solar)
    fuerza, fuerza_txt = _beaufort(v)
    d = {
        "timestamp": timezone.localtime(ts).isoformat(),
        "hace": _hace_txt(ts),
        "punto_rocio": _punto_rocio(t, hr),
        "sensacion": _sensacion(t, hr, v),
        "uv": uvi,
        "uv_categoria": _uv_categoria(uvi),
        "beaufort": fuerza,
        "beaufort_txt": fuerza_txt,
    }

    # Del dia local (medianoche -> ultima lectura): lluvia, radiacion, picos.
    filas = (Lectura.objects
             .filter(estacion=est, timestamp__gte=inicio_dia)
             .order_by("timestamp")
             .values_list("timestamp", "temperatura", "precipitacion",
                          "radiacion_solar", "velocidad_viento"))
    t_max = t_min = rad_pico = v_pico = None
    lluvia_dia = lluvia_1h = 0.0
    rad_j = 0.0                      # W/m2 * s = J/m2, para el total del dia
    prev_r = prev_ts = None
    limite_1h = ts - timedelta(hours=1)
    for f_ts, f_t, f_p, f_r, f_v in filas:
        if f_t is not None:
            t_max = f_t if t_max is None else max(t_max, f_t)
            t_min = f_t if t_min is None else min(t_min, f_t)
        if f_v is not None:
            v_pico = f_v if v_pico is None else max(v_pico, f_v)
        if f_p is not None:
            lluvia_dia += f_p
            if f_ts >= limite_1h:
                lluvia_1h += f_p
        if f_r is not None:
            rad_pico = f_r if rad_pico is None else max(rad_pico, f_r)
            if prev_r is not None and prev_ts is not None:
                dt = (f_ts - prev_ts).total_seconds()
                # Huecos largos no se integran: evita inflar el total.
                if 0 < dt <= 1800:
                    rad_j += (prev_r + f_r) / 2.0 * dt
            prev_r, prev_ts = f_r, f_ts
    d.update({
        "t_max_hoy": round(t_max, 1) if t_max is not None else None,
        "t_min_hoy": round(t_min, 1) if t_min is not None else None,
        "viento_pico_hoy": round(v_pico, 1) if v_pico is not None else None,
        "lluvia_dia": round(lluvia_dia, 1),
        "lluvia_1h": round(lluvia_1h, 2),
        "rad_pico_hoy": round(rad_pico) if rad_pico is not None else None,
        "rad_total_hoy": round(rad_j / 1000.0),   # kJ/m2
    })
    return d


def _derivados_tendencia_ayer(est, ultima):
    """
    Tendencia de presion (hPa/h vs hace 3 h) y comparacion con ayer
    (misma hora). Se separa de _derivados para poder reutilizarlo.
    """
    ts = ultima.timestamp
    d = {}

    p_ahora = (Lectura.objects
               .filter(estacion=est, presion_barometrica__isnull=False,
                       timestamp__gte=ts - timedelta(minutes=30),
                       timestamp__lte=ts)
               .aggregate(m=Avg("presion_barometrica"))["m"])
    p_antes = (Lectura.objects
               .filter(estacion=est, presion_barometrica__isnull=False,
                       timestamp__gte=ts - timedelta(hours=3, minutes=15),
                       timestamp__lte=ts - timedelta(hours=3) + timedelta(minutes=15))
               .aggregate(m=Avg("presion_barometrica"))["m"])
    if p_ahora is not None and p_antes is not None:
        tend = (p_ahora - p_antes) / 3.0
        d["presion_tendencia"] = round(tend, 2)
        d["presion_tendencia_txt"] = ("+" if tend > 0 else "") + f"{tend:.2f}"
        d["presion_tendencia_estado"] = (
            "En aumento" if tend > 0.05
            else "En descenso" if tend < -0.05 else "Estable")
    else:
        d["presion_tendencia"] = None
        d["presion_tendencia_txt"] = None
        d["presion_tendencia_estado"] = None

    # Comparacion con ayer (misma hora): lectura mas cercana a ts - 24 h.
    objetivo = ts - timedelta(hours=24)
    filas_ayer = list(
        Lectura.objects
        .filter(estacion=est,
                timestamp__gte=objetivo - timedelta(minutes=15),
                timestamp__lte=objetivo + timedelta(minutes=15))
        .values_list("timestamp", "temperatura", "humedad_relativa"))
    delta_t = delta_h = None
    if filas_ayer:
        _, ayer_t, ayer_h = min(
            filas_ayer, key=lambda f: abs((f[0] - objetivo).total_seconds()))
        t, hr = ultima.temperatura, ultima.humedad_relativa
        if t is not None and ayer_t is not None:
            delta_t = round(t - ayer_t, 1)
        if hr is not None and ayer_h is not None:
            delta_h = round(hr - ayer_h)
    d["delta_t"] = delta_t
    d["delta_t_txt"] = (("+" if delta_t > 0 else "") + f"{delta_t:.1f}"
                        if delta_t is not None else None)
    d["delta_h"] = delta_h
    d["delta_h_txt"] = (("+" if delta_h > 0 else "") + str(int(delta_h))
                        if delta_h is not None else None)
    return d


def _derivados_completos(est, ultima):
    """Todas las metricas derivadas en un solo diccionario."""
    d = _derivados(est, ultima)
    d.update(_derivados_tendencia_ayer(est, ultima))
    return d


def dashboard(request):
    """
    Vista principal: estado actual de cada estacion.

    La ventana de resumen se ancla a la ultima lectura guardada si los datos
    no estan en vivo (historicos), para que el dashboard no salga vacio.
    """
    estaciones = Estacion.objects.filter(
        codigo__in=ESTACIONES_PRINCIPALES).order_by("codigo")

    tarjetas = []
    for est in estaciones:
        ultima = (Lectura.objects
                  .filter(estacion=est)
                  .order_by("-timestamp")
                  .first())
        if ultima is None:
            tarjetas.append({"estacion": est, "ultima": None,
                             "resumen_24h": {}, "derivados": {},
                             "modo": "vacia"})
            continue
        ahora = timezone.localtime()
        limite_vivo = ahora - timedelta(hours=VENTANA_HORAS + 1)
        if timezone.localtime(ultima.timestamp) >= limite_vivo:
            desde = ahora - timedelta(hours=VENTANA_HORAS)
            modo = "ventana"
        else:
            desde = (timezone.localtime(ultima.timestamp)
                     - timedelta(hours=VENTANA_HORAS))
            modo = "reciente"
        resumen = Lectura.objects.filter(
            estacion=est, timestamp__gte=desde).aggregate(
            n=Count("id"),
            t_min=Min("temperatura"), t_max=Max("temperatura"),
            t_avg=Avg("temperatura"),
            h_avg=Avg("humedad_relativa"),
            p_avg=Avg("presion_barometrica"),
            v_avg=Avg("velocidad_viento"),
            v_max=Max("velocidad_viento"),
            r_avg=Avg("radiacion_solar"),
            r_max=Max("radiacion_solar"),
        )
        tarjetas.append({
            "estacion": est,
            "ultima": ultima,
            "resumen_24h": resumen,
            "derivados": _derivados_completos(est, ultima),
            "modo": modo,
        })

    contexto = {
        "tarjetas": tarjetas,
        "ventana_horas": VENTANA_HORAS,
        "generado": timezone.localtime(),
    }
    return render(request, "dashboard.html", contexto)


@require_GET
def api_ultima(request):
    """Ultima lectura de cada estacion. GET /api/v1/estaciones/ultima/"""
    datos = {}
    for est in Estacion.objects.filter(
            codigo__in=ESTACIONES_PRINCIPALES).order_by("codigo"):
        ultima = (Lectura.objects
                  .filter(estacion=est)
                  .order_by("-timestamp")
                  .first())
        if ultima is None:
            datos[str(est.codigo)] = {"disponible": False, "nombre": est.nombre}
            continue
        datos[str(est.codigo)] = {
            "disponible": True,
            "nombre": est.nombre,
            "timestamp": timezone.localtime(ultima.timestamp).isoformat(),
            "derivados": _derivados_completos(est, ultima),
            **{v: getattr(ultima, v) for v in SERIES},
        }
    return JsonResponse({"ok": True, "estaciones": datos})


@require_GET
def api_pronostico(request):
    """
    Pronostico y visibilidad del modelo Open-Meteo para una estacion.

    GET /api/v1/estaciones/pronostico/?estacion=24

    Es dato del modelo externo (las estaciones no miden visibilidad ni dan
    pronostico); la respuesta va cacheada 10 min para no golpear la API.
    """
    try:
        estacion = Estacion.objects.get(pk=request.GET.get("estacion", ""))
    except (Estacion.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {"ok": False, "error": "parametro 'estacion' invalido"}, status=400)
    if estacion.latitud is None or estacion.longitud is None:
        return JsonResponse({
            "ok": False,
            "error": f"la estacion {estacion.codigo} no tiene coordenadas",
        }, status=404)

    clave = f"pronostico:{estacion.codigo}"
    datos = cache.get(clave)
    if datos is None:
        try:
            datos = pronostico.consultar(
                float(estacion.latitud), float(estacion.longitud))
        except Exception:
            return JsonResponse({
                "ok": False,
                "error": "Open-Meteo no esta disponible en este momento",
            }, status=502)
        cache.set(clave, datos, pronostico.TTL_CACHE_S)

    return JsonResponse({
        "ok": True,
        "estacion": estacion.codigo,
        "nombre": estacion.nombre,
        "fuente": "Open-Meteo (modelo, no la estacion)",
        **datos,
    })


@require_GET
def api_serie(request):
    """
    Serie temporal para las graficas.

    GET /api/v1/estaciones/serie/?estacion=24
    GET /api/v1/estaciones/serie/?estacion=24&modo=reciente

    Hay dos modos:
      - modo "ventana" (por defecto): ultimas 24 h hasta ahora.
      - modo "reciente": 24 h anteriores a la ultima lectura guardada.
        Se usa cuando el dashboard muestra historicos sin datos en vivo,
        porque la ventana "hasta ahora" saldria vacia.

    Los puntos se agrupan en Python, no en SQL: con 288 puntos (5 min) o
    5.400 (demo a 16 s) el costo es despreciable y el codigo queda portable
    entre SQLite y PostgreSQL.
    """
    try:
        estacion = Estacion.objects.get(pk=request.GET.get("estacion", ""))
    except (Estacion.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {"ok": False, "error": "parametro 'estacion' invalido"}, status=400)
    if estacion.codigo not in ESTACIONES_PRINCIPALES:
        # La 99 vive en su modulo (/ambient/); no se sirve por aqui.
        return JsonResponse(
            {"ok": False,
             "error": "estacion fuera del panel principal (ver /ambient/)"},
            status=404)

    ultima = (Lectura.objects
              .filter(estacion=estacion)
              .order_by("-timestamp")
              .first())
    if ultima is None:
        return JsonResponse({
            "ok": False,
            "error": f"la estacion {estacion.codigo} no tiene lecturas",
        }, status=404)

    modo = (request.GET.get("modo", "ventana") or "ventana").lower()
    if modo == "reciente":
        # 24 h anteriores a la ultima lectura guardada.
        hasta = timezone.localtime(ultima.timestamp)
    else:
        modo = "ventana"
        hasta = timezone.localtime()
    desde = hasta - timedelta(hours=VENTANA_HORAS)

    filas = (Lectura.objects
             .filter(estacion=estacion, timestamp__gte=desde,
                     timestamp__lte=hasta)
             .order_by("timestamp")
             .values("timestamp", *SERIES))
    n = filas.count()
    paso_min = _minutos_agrupacion()

    # Se acumulan suma y conteo por cubo para promediar al final.
    cubos = {}
    for fila in filas.iterator(chunk_size=2000):
        ts_local = timezone.localtime(fila["timestamp"])
        minuto = (ts_local.minute // paso_min) * paso_min
        cubo = ts_local.replace(minute=minuto, second=0, microsecond=0)
        if cubo not in cubos:
            cubos[cubo] = {"sumas": {}, "n": {}}
        for var in SERIES:
            valor = fila[var]
            if valor is None:
                continue
            cubos[cubo]["sumas"][var] = cubos[cubo]["sumas"].get(var, 0.0) + valor
            cubos[cubo]["n"][var] = cubos[cubo]["n"].get(var, 0) + 1

    serie = []
    for cubo in sorted(cubos):
        fila_out = {"t": cubo.isoformat()}
        sumas = cubos[cubo]["sumas"]
        conteos = cubos[cubo]["n"]
        for var in SERIES:
            if var in sumas:
                fila_out[var] = round(sumas[var] / conteos[var], 2)
            else:
                fila_out[var] = None
        serie.append(fila_out)

    return JsonResponse({
        "ok": True,
        "estacion": estacion.codigo,
        "nombre": estacion.nombre,
        "modo": modo,
        "ventana_horas": VENTANA_HORAS,
        "ventana_desde": desde.isoformat(),
        "ventana_hasta": hasta.isoformat(),
        "lecturas_en_ventana": n,
        "minutos_por_punto": paso_min,
        "puntos": len(serie),
        "series": SERIES,
        "datos": serie,
    })


# ---------- historial: estadisticas por ano, mes, dia y hora ----------

MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic")

# El historial historico no cambia; 10 min cubre tambien los datos en vivo
# que puedan llegar por el endpoint de recepcion.
TTL_HISTORIAL_S = 600

# Estadisticas comunes de cada cubo del historial (y del resumen global).
STATS_HISTORIAL = dict(
    n=Count("id"),
    t_min=Min("temperatura"), t_max=Max("temperatura"),
    t_avg=Avg("temperatura"),
    h_avg=Avg("humedad_relativa"),
    lluvia=Sum("precipitacion"),
    p_avg=Avg("presion_barometrica"),
    v_avg=Avg("velocidad_viento"), v_max=Max("velocidad_viento"),
    r_avg=Avg("radiacion_solar"), r_max=Max("radiacion_solar"),
    primera=Min("timestamp"), ultima=Max("timestamp"),
)


def _entero_opcional(texto, minimo, maximo):
    """Parametro entero opcional y validado; None si viene vacio."""
    if texto in (None, ""):
        return None
    try:
        valor = int(texto)
    except (TypeError, ValueError):
        raise ValueError(f"parametro invalido: {texto!r}")
    if not (minimo <= valor <= maximo):
        raise ValueError(f"fuera de rango: {texto!r}")
    return valor


def _fila_historial(g, nivel):
    """
    Convierte un grupo agregado en fila JSON segun el nivel.

    g["cubo"] es la cadena ISO que agrupo SQL:
    "2004" | "2004-05" | "2004-05-17" | "2004-05-17 14:00".
    clave: identificador del cubo (para migas y CSV).
    etiqueta: como se muestra en la tabla y en los selectores.
    anio/mes/dia/hora: componentes para poblar los selectores en cascada.
    """
    cubo = g["cubo"]
    anio, mes, dia, hora = int(cubo[:4]), None, None, None
    if nivel == "anio":
        clave, etiqueta = cubo, cubo
    elif nivel == "mes":
        mes = int(cubo[5:7])
        clave = cubo
        etiqueta = f"{MESES_ES[mes - 1]} {anio}"
    elif nivel == "dia":
        mes, dia = int(cubo[5:7]), int(cubo[8:10])
        clave = cubo
        etiqueta = f"{dia} {MESES_ES[mes - 1]} {anio}"
    else:                                   # hora
        mes, dia, hora = int(cubo[5:7]), int(cubo[8:10]), cubo[11:16]
        clave = cubo
        etiqueta = hora
    fila = {
        "clave": clave,
        "etiqueta": etiqueta,
        "anio": anio,
        "mes": mes,
        "dia": dia,
        "hora": hora,
    }
    for campo in ("n", "t_min", "t_max", "t_avg", "h_avg", "lluvia",
                  "p_avg", "v_avg", "v_max", "r_avg", "r_max"):
        valor = g[campo]
        if valor is not None and campo != "n":
            valor = round(valor, 2)
        fila[campo] = valor
    return fila


def _resumen_historial(qs):
    """Estadisticas globales del conjunto filtrado actual."""
    r = qs.aggregate(**STATS_HISTORIAL)
    for campo in ("t_min", "t_max", "t_avg", "h_avg", "lluvia", "p_avg",
                  "v_avg", "v_max", "r_avg", "r_max"):
        if r[campo] is not None:
            r[campo] = round(r[campo], 2)
    r["primera"] = (timezone.localtime(r["primera"]).isoformat()
                    if r["primera"] else None)
    r["ultima"] = (timezone.localtime(r["ultima"]).isoformat()
                   if r["ultima"] else None)
    return r


def _offset_horas():
    """Desfase en horas de la zona del proyecto (+/-) para el SQL.

    America/Bogota es UTC-5 fijo (sin horario de verano desde 1992), asi
    que un unico desfase por consulta es correcto para toda la serie.
    """
    return int(timezone.localtime().utcoffset().total_seconds() // 3600)


_CUBO_FORMATOS = {
    # El %% no es un error: el cursor de SQLite lo convierte a % cuando la
    # consulta lleva parametros (siempre los lleva: el filtro por estacion).
    # Si se escribiera % a secas, el cursor DEBUG de Django reventaria al
    # interpolar la consulta con los parametros para el log (sql % params).
    "anio": "%%Y",
    "mes": "%%Y-%%m",
    "dia": "%%Y-%%m-%%d",
    "hora": "%%Y-%%m-%%d %%H:00",
}


def _agrupar_por_cubo(qs, nivel):
    """
    Agrupa las lecturas en cubos de ano/mes/dia/hora con SQL nativo.

    Trunc* de Django en SQLite es una funcion Python por fila: con 2,3 M
    de lecturas de La Nubia tardaba ~15 s por consulta. strftime es nativo
    del motor (mide ~3 s) y como las fechas son ISO, el orden lexicografico
    de las claves queda cronologico sin esfuerzo.
    """
    mod = f"{_offset_horas():+d} hours"
    sql = f"strftime('{_CUBO_FORMATOS[nivel]}', timestamp, '{mod}')"
    return (qs
            .annotate(cubo=RawSQL(sql, [], output_field=CharField()))
            .values("cubo")
            .annotate(**STATS_HISTORIAL)
            .order_by("cubo"))


@require_GET
def api_historial(request):
    """
    Historial estadistico de una estacion, en niveles de drill-down.

    GET /api/v1/estaciones/historial/?estacion=24
        -> una fila por anio con datos
    GET ...?estacion=24&anio=2026            -> por mes
    GET ...?estacion=24&anio=2026&mes=9      -> por dia
    GET ...?estacion=24&anio=2026&mes=9&dia=15 -> por hora
    GET ...&anio&mes&dia&crudos=1             -> lecturas crudas de ese dia

    Los cubos se calculan con Trunc* en la zona America/Bogota, asi el
    dia "15" es el dia local de la estacion, no el del servidor.
    """
    try:
        estacion = Estacion.objects.get(pk=request.GET.get("estacion", ""))
    except (Estacion.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {"ok": False, "error": "parametro 'estacion' invalido"}, status=400)
    if estacion.codigo not in ESTACIONES_PRINCIPALES:
        # La 99 vive en su modulo (/ambient/); no entra al historial.
        return JsonResponse(
            {"ok": False,
             "error": "estacion fuera del panel principal (ver /ambient/)"},
            status=404)

    try:
        anio = _entero_opcional(request.GET.get("anio"), 1900, 2200)
        mes = _entero_opcional(request.GET.get("mes"), 1, 12)
        dia = _entero_opcional(request.GET.get("dia"), 1, 31)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    # La cascada exige el nivel previo: no hay mes sin ano, ni dia sin mes.
    if mes is not None and anio is None:
        return JsonResponse(
            {"ok": False, "error": "se necesita 'anio' para filtrar por mes"},
            status=400)
    if dia is not None and (anio is None or mes is None):
        return JsonResponse(
            {"ok": False, "error": "se necesitan 'anio' y 'mes' para filtrar por dia"},
            status=400)

    qs = Lectura.objects.filter(estacion=estacion)
    if anio is not None:
        qs = qs.filter(timestamp__year=anio)
    if mes is not None:
        qs = qs.filter(timestamp__month=mes)
    if dia is not None:
        qs = qs.filter(timestamp__day=dia)

    nivel = ("hora" if dia is not None else
             "dia" if mes is not None else
             "mes" if anio is not None else "anio")
    crudos = request.GET.get("crudos") == "1"

    # Cada periodo historico es inmutable: la respuesta se cachea. Los
    # datos en vivo del endpoint de recepcion quedan cubiertos por la
    # ventana de 10 min (igual que el pronostico).
    clave_cache = (f"historial:{estacion.codigo}:"
                   f"{'crudos' if crudos else nivel}:{anio}:{mes}:{dia}")
    datos = cache.get(clave_cache)
    if datos is not None:
        return JsonResponse({
            "ok": True, "estacion": estacion.codigo,
            "nombre": estacion.nombre, **datos,
        })

    if crudos:
        if anio is None or mes is None or dia is None:
            return JsonResponse({
                "ok": False,
                "error": "los datos crudos exigen anio, mes y dia completos",
            }, status=400)
        columnas = ("timestamp", *SERIES, "direccion_viento")
        filas = [
            {"t": timezone.localtime(f["timestamp"]).isoformat(),
             **{v: f[v] for v in SERIES},
             "direccion_viento": f["direccion_viento"]}
            for f in qs.order_by("timestamp").values(*columnas)
        ]
        datos = {
            "nivel": "crudos",
            "clave": f"{anio:04d}-{mes:02d}-{dia:02d}",
            "resumen": _resumen_historial(qs),
            "filas": filas,
        }
    else:
        filas = [_fila_historial(g, nivel)
                 for g in _agrupar_por_cubo(qs, nivel)]
        datos = {
            "nivel": nivel,
            "anio": anio,
            "mes": mes,
            "dia": dia,
            "resumen": _resumen_historial(qs),
            "filas": filas,
        }

    cache.set(clave_cache, datos, TTL_HISTORIAL_S)
    return JsonResponse({
        "ok": True,
        "estacion": estacion.codigo,
        "nombre": estacion.nombre,
        **datos,
    })
