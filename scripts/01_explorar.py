# -*- coding: utf-8 -*-
"""Exploracion de las estaciones. Salida: resumen en consola."""
import pandas as pd
import numpy as np
import sys

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal\Est_Datos"
ARCHIVOS = {
    "La Nubia (24)": rf"{BASE}\24-La Nubia.csv",
    "Palogrande-Postgrados (29)": rf"{BASE}\29-Palogrande-Postgrados.csv",
}

COLS = ["fecha", "tiempo", "precipitacion", "temperatura", "brillo",
        "humedad_relativa", "nivel", "caudal", "velocidad_viento",
        "direccion_viento", "presion_barometrica", "evapotranspiracion",
        "radiacion_solar"]

for nombre, ruta in ARCHIVOS.items():
    print("=" * 78)
    print(f"ESTACION: {nombre}")
    print(f"archivo  : {ruta}")
    print("=" * 78)

    nonnull = {c: 0 for c in COLS}
    total = 0
    mins, maxs = {}, {}
    fechas = []
    tserie = []

    for chunk in pd.read_csv(ruta, chunksize=250_000, dtype=str,
                             keep_default_na=True, na_values=[""]):
        total += len(chunk)
        for c in COLS:
            nonnull[c] += int(chunk[c].notna().sum())
        # solo necesitamos fecha/tiempo para el analisis temporal (submuestreo)
        sub = chunk.iloc[::20]
        fechas.append(sub["fecha"])
        num = chunk.apply(pd.to_numeric, errors="coerce")
        for c in COLS[2:]:
            s = num[c]
            if s.notna().any():
                lo, hi = float(s.min()), float(s.max())
                if c in mins:
                    mins[c] = min(mins[c], lo)
                    maxs[c] = max(maxs[c], hi)
                else:
                    mins[c], maxs[c] = lo, hi

    print(f"\nfilas totales: {total:,}")

    print("\n-- completitud por columna --")
    for c in COLS:
        n = nonnull[c]
        pct = 100.0 * n / total if total else 0
        flag = "  <-- VACIA" if n == 0 else ""
        print(f"  {c:<22} {n:>11,} ({pct:5.1f}%){flag}")

    print("\n-- rangos numericos --")
    for c in COLS[2:]:
        if c in mins:
            print(f"  {c:<22} min={mins[c]:>10.2f}   max={maxs[c]:>10.2f}")
        else:
            print(f"  {c:<22} sin datos")

    f = pd.concat(fechas)
    d = pd.to_datetime(f, format="%Y-%m-%d", errors="coerce")
    print("\n-- rango temporal (submuestra 1/20) --")
    print(f"  primera fecha valida: {d.min()}")
    print(f"  ultima  fecha valida: {d.max()}")
    print(f"  fechas no parseables : {int(d.isna().sum()):,}")
    print(f"  fechas unicas        : {d.dt.date.nunique():,}")
    print()
