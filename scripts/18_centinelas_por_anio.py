# -*- coding: utf-8 -*-
"""Verifica donde estan los centinelas por anio y si el tramo reciente es limpio."""
import csv
from collections import Counter

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
RUTA = BASE + r"\Est_Datos\24-La Nubia.csv"

tot = Counter()
h255 = Counter()
w113 = Counter()
d507 = Counter()
p0 = Counter()

with open(RUTA, newline="", encoding="utf-8") as f:
    for fila in csv.DictReader(f):
        anio = (fila.get("fecha") or "")[:4]
        if not anio.isdigit():
            continue
        tot[anio] += 1
        try:
            h = float((fila.get("humedad_relativa") or "").strip() or "nan")
        except ValueError:
            h = float("nan")
        try:
            w = float((fila.get("velocidad_viento") or "").strip() or "nan")
        except ValueError:
            w = float("nan")
        try:
            d = float((fila.get("direccion_viento") or "").strip() or "nan")
        except ValueError:
            d = float("nan")
        try:
            p = float((fila.get("presion_barometrica") or "").strip() or "nan")
        except ValueError:
            p = float("nan")
        if h == 255:
            h255[anio] += 1
        if abs(w - 113.99) < 0.005:
            w113[anio] += 1
        if d == 507:
            d507[anio] += 1
        if p == 0:
            p0[anio] += 1

print("anio      filas    hum255   vien113    dir507    pres0")
for anio in sorted(tot):
    print(f"{anio}  {tot[anio]:>8,}  {h255[anio]:>7,}  {w113[anio]:>8,}  "
          f"{d507[anio]:>7,}  {p0[anio]:>6,}")

rec = [a for a in tot if a >= "2026"]
print()
print("tramo 2026: filas =", sum(tot[a] for a in rec),
      "| hum255 =", sum(h255[a] for a in rec),
      "| vien113 =", sum(w113[a] for a in rec),
      "| dir507 =", sum(d507[a] for a in rec),
      "| pres0 =", sum(p0[a] for a in rec))
