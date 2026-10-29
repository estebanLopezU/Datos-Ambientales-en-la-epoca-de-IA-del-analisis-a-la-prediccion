# -*- coding: utf-8 -*-
"""Predictor ML puro Python (kNN) para el modulo Ambient."""
import json
import math
import os
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from estaciones.ml.features import (
    VARIABLES, HORIZONTES_H, cargar_series, construir_dataset, MIN_MUESTRAS,
)
from estaciones.models import ConsolaAmbient, Estacion

MODELOS_DIR = os.path.join(os.path.dirname(__file__), "modelos")
os.makedirs(MODELOS_DIR, exist_ok=True)
CACHE_PRED = 900
K = 15


def _ruta(device_id):
    safe = "".join(c for c in device_id if c.isalnum() or c in "-_") or "global"
    return os.path.join(MODELOS_DIR, f"{safe}.json")


def _estacion_de_consola(device_id):
    try:
        c = ConsolaAmbient.objects.get(device_id=device_id)
        if c.estacion:
            return c.estacion.codigo
    except ConsolaAmbient.DoesNotExist:
        pass
    if str(device_id).upper() in ("LUNA", "DESCONOCIDA"):
        return 99
    return None


def _normalizar(X):
    n = len(X)
    if n == 0:
        return X, [], []
    d = len(X[0])
    means = [sum(row[j] for row in X) / n for j in range(d)]
    stds = []
    for j in range(d):
        var = sum((row[j] - means[j]) ** 2 for row in X) / n
        stds.append(math.sqrt(var) if var > 0 else 1.0)
    Xn = [[(row[j] - means[j]) / stds[j] for j in range(d)] for row in X]
    return Xn, means, stds


def entrenar(device_id=None, global_all=False):
    if global_all:
        series_all = []
        for est in Estacion.objects.all():
            s = cargar_series(est.codigo)
            if s:
                series_all.extend(s)
        series = series_all
        est_code = None
    else:
        codigo = _estacion_de_consola(device_id)
        if codigo is None:
            return {"ok": False, "motivo": "consola sin estacion"}
        series = cargar_series(codigo)
        est_code = codigo
    dataset = construir_dataset(series)
    if len(dataset) < MIN_MUESTRAS:
        return {"ok": False, "motivo": f"pocas muestras ({len(dataset)})"}

    X = [d["features"] for d in dataset]
    Xn, means, stds = _normalizar(X)
    muestras = dataset[-2000:]
    Xs = [d["features"] for d in muestras]
    ys = [d["targets"] for d in muestras]
    Xsn, means, stds = _normalizar(Xs)

    meta = {
        "device_id": device_id if device_id else "GLOBAL",
        "estacion": est_code,
        "n_muestras": len(dataset),
        "features_n": len(X[0]),
        "horizontes": HORIZONTES_H,
        "variables": VARIABLES,
        "entrenado_en": timezone.now().isoformat(),
        "means": means,
        "stds": stds,
    }
    bundle = {"meta": meta, "X": Xsn, "y": ys, "means": means, "stds": stds}
    with open(_ruta(device_id if device_id else "GLOBAL"), "w", encoding="utf-8") as f:
        json.dump(bundle, f)
    return {"ok": True, "n_muestras": len(dataset), "entrenado_en": meta["entrenado_en"]}
def _cargar(device_id):
    for key in (device_id, "GLOBAL"):
        path = _ruta(key)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f), key
            except Exception:
                continue
    return None, None


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(len(a))))


def predecir(device_id, horizonte=6):
    cache_key = f"ml_pred_{device_id}_{horizonte}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    codigo = _estacion_de_consola(device_id)
    if codigo is None:
        codigo = 99
    series = cargar_series(codigo)
    if not series:
        res = {"ok": False, "motivo": "sin datos", "fallback": True}
        cache.set(cache_key, res, CACHE_PRED)
        return res

    dataset = construir_dataset(series)
    bundle, usado = _cargar(device_id)
    ahora = series[-1]["timestamp"]

    preds = []
    if bundle is not None and bundle.get("X") and dataset:
        Xn = bundle["X"]
        ys = bundle["y"]
        means = bundle["means"]
        stds = bundle["stds"]
        if dataset:
            last_feats = dataset[-1]["features"]
            last_n = [(last_feats[j] - means[j]) / (stds[j] if stds[j] else 1.0)
                      for j in range(len(last_feats))]
            dists = sorted(range(len(Xn)), key=lambda i: _dist(Xn[i], last_n))
            neigh = dists[:K]
            agg = {f"{v}_h{h}": [] for v in VARIABLES for h in HORIZONTES_H}
            for i in neigh:
                for key, val in ys[i].items():
                    agg[key].append(val)
            for h in HORIZONTES_H:
                if h > horizonte:
                    continue
                bloque = {}
                for v in VARIABLES:
                    key = f"{v}_h{h}"
                    vals = agg.get(key, [])
                    if vals:
                        m = sum(vals) / len(vals)
                        var = sum((x - m) ** 2 for x in vals) / len(vals)
                        conf = math.sqrt(var)
                        bloque[v] = {"valor": round(m, 2), "confianza": round(conf, 2)}
                    else:
                        bloque[v] = {"valor": None, "confianza": None}
                preds.append({"hora": (ahora + timedelta(hours=h)).isoformat(),
                              "horizonte_h": h, **bloque})
        modelo_usado = usado if usado else "fallback"
        fallback = False
    else:
        last = series[-1]
        for h in HORIZONTES_H:
            if h > horizonte:
                continue
            bloque = {}
            for v in VARIABLES:
                val = last.get(v)
                bloque[v] = {"valor": (round(float(val), 2) if val is not None else None),
                             "confianza": None}
            preds.append({"hora": (ahora + timedelta(hours=h)).isoformat(),
                          "horizonte_h": h, **bloque})
        modelo_usado = "fallback"
        fallback = True

    prob_lluvia = None
    try:
        p0 = preds[0].get("precipitacion", {}).get("valor") if preds else None
        if p0 is not None:
            prob_lluvia = min(95, max(5, int(p0 * 20 + 10)))
    except Exception:
        prob_lluvia = None

    meta = bundle.get("meta", {}) if bundle else {}
    res = {
        "ok": True,
        "consola": device_id,
        "modelo_usado": modelo_usado,
        "entrenado_en": meta.get("entrenado_en"),
        "metricas": {"n_muestras": meta.get("n_muestras")},
        "ahora": ahora.isoformat(),
        "horizonte": horizonte,
        "predicciones": preds,
        "prob_lluvia_pct": prob_lluvia,
        "fallback": fallback,
    }
    cache.set(cache_key, res, CACHE_PRED)
    return res
