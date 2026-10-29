# -*- coding: utf-8 -*-
"""Construccion de features a partir del historico de Lecturas (puro Python)."""
import math

from estaciones.models import Lectura

VARIABLES = ["temperatura", "humedad_relativa", "precipitacion",
              "presion_barometrica", "velocidad_viento", "direccion_viento",
              "radiacion_solar"]
LAGS_H = [1, 2, 3, 6, 12, 24]
HORIZONTES_H = [1, 3, 6]
MIN_MUESTRAS = 200


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cargar_series(estacion_codigo):
    qs = (Lectura.objects.filter(estacion__codigo=estacion_codigo)
          .order_by("-timestamp")
          .values("timestamp", *VARIABLES)[:5000])
    rows = list(qs)
    rows.reverse()
    if not rows:
        return []
    buckets = {}
    for r in rows:
        ts = r["timestamp"]
        key = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(key, []).append(r)
    out = []
    for key in sorted(buckets):
        rs = buckets[key]
        rec = {"timestamp": key}
        for v in VARIABLES:
            vals = [_to_float(r[v]) for r in rs]
            vals = [x for x in vals if x is not None]
            rec[v] = (sum(vals) / len(vals)) if vals else None
        out.append(rec)
    return out


def _ciclico(valor, periodo):
    ang = 2 * math.pi * valor / periodo
    return math.sin(ang), math.cos(ang)


def construir_dataset(series):
    n = len(series)
    if n < max(LAGS_H) + max(HORIZONTES_H) + 5:
        return []
    dataset = []
    for i in range(max(LAGS_H), n - max(HORIZONTES_H)):
        s = series[i]
        feats = []
        ok = True
        for v in VARIABLES:
            for lag in LAGS_H:
                val = series[i - lag].get(v)
                if val is None:
                    ok = False
                    break
                feats.append(val)
            if not ok:
                break
            window3 = [series[i - k].get(v) for k in range(1, 4)]
            window6 = [series[i - k].get(v) for k in range(1, 7)]
            if any(x is None for x in window3 + window6):
                ok = False
                break
            feats.append(sum(window3) / 3)
            feats.append(sum(window6) / 6)
            m = sum(window6) / 6
            var = sum((x - m) ** 2 for x in window6) / 6
            feats.append(math.sqrt(var))
        if not ok:
            continue
        ts = s["timestamp"]
        sin_h, cos_h = _ciclico(ts.hour, 24)
        sin_d, cos_d = _ciclico(ts.weekday(), 7)
        sin_m, cos_m = _ciclico(ts.month, 12)
        feats += [sin_h, cos_h, sin_d, cos_d, sin_m, cos_m]
        targets = {}
        target_ok = True
        for h in HORIZONTES_H:
            for v in VARIABLES:
                val = series[i + h].get(v)
                if val is None:
                    target_ok = False
                    break
                targets[f"{v}_h{h}"] = val
            if not target_ok:
                break
        if not target_ok:
            continue
        dataset.append({"ts": ts.isoformat(), "features": feats, "targets": targets})
    return dataset
