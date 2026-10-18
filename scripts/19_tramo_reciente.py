# -*- coding: utf-8 -*-
"""Verifica si el tramo sept-oct 2026 trae centinelas en ambas estaciones."""
import csv

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
ARCHIVOS = {
    24: BASE + r"\Est_Datos\24-La Nubia.csv",
    29: BASE + r"\Est_Datos\29-Palogrande-Postgrados.csv",
}
DESDE = "2026-09-01"


def num(txt):
    try:
        return float((txt or "").strip() or "nan")
    except ValueError:
        return float("nan")


for codigo, ruta in ARCHIVOS.items():
    tot = h255 = w113 = p0 = 0
    primera = ultima = None
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            fecha = (fila.get("fecha") or "").strip()
            if fecha < DESDE:
                continue
            tot += 1
            ts = fecha + " " + (fila.get("tiempo") or "").strip()
            primera = primera or ts
            ultima = ts
            if num(fila.get("humedad_relativa")) == 255:
                h255 += 1
            if abs(num(fila.get("velocidad_viento")) - 113.99) < 0.005:
                w113 += 1
            if num(fila.get("presion_barometrica")) == 0:
                p0 += 1
    print(f"estacion {codigo}: filas={tot:,} desde={primera} hasta={ultima}")
    print(f"  hum255={h255:,}  vien113={w113:,}  pres0={p0:,}")
