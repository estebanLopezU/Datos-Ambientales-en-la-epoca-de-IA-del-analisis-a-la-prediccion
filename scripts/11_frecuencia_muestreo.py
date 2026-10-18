# -*- coding: utf-8 -*-
"""
Analiza la frecuencia real de muestreo de cada estacion.

Motivo: el profesor plantea enviar datos cada 16 segundos, pero los CSV
historicos son cada 5 minutos. Hay que medir el intervalo REAL del tramo mas
reciente para dimensionar el endpoint y la ventana de 24 horas.
"""
import csv
from collections import Counter
from datetime import datetime

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal\Est_Datos"
ARCHIVOS = [
    ("24 La Nubia", rf"{BASE}\24-La Nubia.csv"),
    ("29 Palogrande", rf"{BASE}\29-Palogrande-Postgrados.csv"),
]

for nombre, ruta in ARCHIVOS:
    print("=" * 74)
    print(f"ESTACION {nombre}")
    print("=" * 74)

    ultimas = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ultimas.append((row["fecha"], row["tiempo"]))
            if len(ultimas) > 6000:      # ventana deslizante: nos quedamos con el final
                ultimas.pop(0)

    fechas = [datetime.strptime(f + " " + t, "%Y-%m-%d %H:%M:%S")
              for f, t in ultimas]

    deltas = [(b - a).total_seconds() for a, b in zip(fechas, fechas[1:])]
    print(f"\ntramo analizado : {fechas[0]}  ->  {fechas[-1]}")
    print(f"registros       : {len(fechas):,}")

    horas = (fechas[-1] - fechas[0]).total_seconds() / 3600
    print(f"duracion        : {horas:.1f} h")

    # Intervalo modal y dispersion
    comunes = Counter(deltas).most_common(6)
    print("\nintervalos mas frecuentes (segundos -> cuantas veces):")
    for seg, n in comunes:
        print(f"  {seg:>8.0f} s  x{n:,}")

    positivos = [d for d in deltas if d > 0]
    if positivos:
        mediana = sorted(positivos)[len(positivos) // 2]
        print(f"\nintervalo mediano : {mediana:.0f} s ({mediana/60:.1f} min)")
        print(f"intervalo minimo  : {min(positivos):.0f} s")
        print(f"intervalo maximo  : {max(positivos):.0f} s ({max(positivos)/60:.0f} min)")

    irreg = sum(1 for d in deltas if d != (comunes[0][0] if comunes else 300))
    print(f"intervalos atipicos: {irreg:,} de {len(deltas):,} "
          f"({100*irreg/max(len(deltas),1):.1f} %)")

    # Cuanto ocuparia una ventana de 24 h a distintas frecuencias
    print("\nregistros en una ventana de 24 h:")
    for etiqueta, seg in [("16 s (lo que pide el profesor)", 16),
                          ("60 s", 60),
                          ("5 min (frecuencia historica)", 300)]:
        n = 86400 // seg
        print(f"  {etiqueta:<30} {n:>6,} registros/estacion"
              f"  |  {2*n:>7,} con las 2 estaciones")

    # Volumen mensual de escritura a 16 s
    n16 = 86400 // 16
    print(f"\na 16 s: {n16*30:,} registros/estacion/mes "
          f"| {n16*30*2:,} con 2 estaciones")
    print()
