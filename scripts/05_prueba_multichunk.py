# -*- coding: utf-8 -*-
"""
Prueba con multiples chunks y multiples anos, incluido el cruce de fin de ano.

Es la prueba que detecta el bug de indice duplicado en las agregaciones:
con un solo chunk el indice por ano ya es unico y el error no se manifiesta.
"""
import importlib.util
import os
import shutil

import numpy as np
import pandas as pd
import openpyxl

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
PRU = os.path.join(BASE, "_prueba_multichunk")
DATOS = os.path.join(PRU, "Est_Datos")
SALIDA = os.path.join(PRU, "Excel_Organizado")
CSV = os.path.join(DATOS, "29-Palogrande-Postgrados.csv")
XLSX = os.path.join(SALIDA, "Estacion_29_Palogrande_Postgrados.xlsx")

VARS = ["precipitacion", "temperatura", "humedad_relativa", "nivel", "caudal",
        "velocidad_viento", "direccion_viento", "presion_barometrica",
        "evapotranspiracion", "radiacion_solar", "brillo"]

# Anos con cantidad de dias distinta, para que cada chunk agrupe varios anos.
ANIOS = [(2003, 4), (2004, 3), (2005, 2)]
REG_POR_DIA = 288          # 5 minutos
FILAS_POR_CHUNK = 500      # pequeno a proposito: obliga a muchos chunks

if os.path.isdir(PRU):
    shutil.rmtree(PRU)
os.makedirs(DATOS, exist_ok=True)

# Genera el CSV de prueba y guarda los agregados esperados.
rng = np.random.default_rng(7)
esperado = {}
with open(CSV, "w", encoding="utf-8", newline="") as f:
    f.write('"fecha","tiempo",' + ",".join(f'"{v}"' for v in VARS) + "\n")
    n = 0
    for anio, dias in ANIOS:
        for dia in range(dias):
            fecha = f"{anio}-01-{dia + 1:02d}"
            for k in range(REG_POR_DIA):
                tiempo = f"{k * 5 // 60:02d}:{k * 5 % 60:02d}:00"
                temp = round(float(rng.uniform(10, 25)), 2)
                precip = round(float(rng.uniform(0, 5)), 2)
                hum = int(rng.integers(50, 100))
                # Algunos huecos a proposito, y algun centinela.
                if k % 97 == 0:
                    temp = ""
                if k % 211 == 0:
                    hum = 255          # centinela
                fila = [fecha, tiempo, precip, temp, "", hum, "", "",
                        round(float(rng.uniform(0, 5)), 2), int(rng.integers(0, 360)),
                        round(float(rng.uniform(580, 600)), 2),
                        round(float(rng.uniform(0, 3)), 2),
                        round(float(rng.uniform(0, 900)), 1)]
                f.write(",".join(f'"{c}"' if i < 2 else str(c)
                                 for i, c in enumerate(fila)) + "\n")
                n += 1
        esperado[anio] = dias * REG_POR_DIA

print(f"CSV de prueba: {n:,} filas, {len(ANIOS)} anos, chunk={FILAS_POR_CHUNK:,}")
print(f"  registros por ano esperados: {esperado}")
print(f"  dias por ano esperados     : {dict(ANIOS)}")

spec = importlib.util.spec_from_file_location(
    "organizador", os.path.join(BASE, "scripts", "02_organizar_excel.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.SALIDA = SALIDA
mod.CHUNK = FILAS_POR_CHUNK
mod.ESTACIONES = [{"codigo": "29", "nombre": "Palogrande-Postgrados",
                   "csv": CSV, "xlsx": XLSX}]
mod.main()

# --- Comprobaciones ---
wb = openpyxl.load_workbook(XLSX, read_only=True)
hojas = wb.sheetnames
print("\nhojas:", hojas)
for anio, esp in esperado.items():
    assert str(anio) in hojas, f"falta la hoja del ano {anio}"
    ws = wb[str(anio)]
    filas = ws.max_row - 1
    print(f"  hoja {anio}: {filas:,} filas (esperadas {esp:,})")
    assert filas == esp, f"ano {anio}: {filas} != {esp}"

ws = wb["Resumen_Anual"]
print("\nResumen_Anual:")
for fila in ws.iter_rows(min_row=1, values_only=True):
    print("  ", ["-" if v is None else v for v in fila])
    if fila[0] == ANIOS[0][0]:
        assert fila[1] == esperado[ANIOS[0][0]], "registros del resumen incorrectos"
        assert fila[2] == ANIOS[0][1], \
            f"dias con datos incorrecto: {fila[2]} != {ANIOS[0][1]} (doble conteo por chunk)"

# Cada ano debe reportar sus dias reales, no la suma por chunk.
for fila in ws.iter_rows(min_row=2, values_only=True):
    esperado_dias = dict(ANIOS)[fila[0]]
    assert fila[2] == esperado_dias, \
        f"ano {fila[0]}: dias={fila[2]} != {esperado_dias}"
    print(f"  ano {fila[0]}: {fila[1]:,} registros, {fila[2]} dias  OK")

# La temperatura media debe ser un numero, no una celda vacia enmascarada.
for fila in ws.iter_rows(min_row=2, values_only=True):
    assert isinstance(fila[3], (int, float)), \
        f"Temp. media no numerica para {fila[0]}: {fila[3]!r} (indice duplicado?)"
    assert isinstance(fila[1], (int, float)), f"Registros no numerico para {fila[0]}"

print("\nOK: multi-chunk y multi-ano correctos")
