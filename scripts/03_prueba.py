# -*- coding: utf-8 -*-
"""Prueba rapida: recorta el CSV original y ejecuta el organizador sobre el recorte.

Importa el modulo real (sin parchear su texto) y sobrescribe la configuracion,
para validar exactamente el codigo de produccion.
"""
import importlib.util
import os

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
ORIG = os.path.join(BASE, "Est_Datos", "24-La Nubia.csv")
PRU = os.path.join(BASE, "_prueba")
CSV_PRU = os.path.join(PRU, "24-La Nubia.csv")
SALIDA_PRU = os.path.join(PRU, "Excel_Organizado")
N = 40_000

os.makedirs(PRU, exist_ok=True)
with open(ORIG, "r", encoding="utf-8") as f, \
     open(CSV_PRU, "w", encoding="utf-8") as o:
    o.write(f.readline())          # cabecera
    for i, linea in enumerate(f):
        if i >= N:
            break
        o.write(linea)
print(f"CSV de prueba: {N:,} filas -> {CSV_PRU}")

# Importa el modulo real y sobrescribe la configuracion.
spec = importlib.util.spec_from_file_location(
    "organizador", os.path.join(BASE, "scripts", "02_organizar_excel.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.SALIDA = SALIDA_PRU
mod.ESTACIONES = [{
    "codigo": "24",
    "nombre": "La Nubia",
    "csv": CSV_PRU,
    "xlsx": os.path.join(SALIDA_PRU, "Estacion_24_La_Nubia.xlsx"),
}]
mod.main()

xlsx = os.path.join(SALIDA_PRU, "Estacion_24_La_Nubia.xlsx")
print(f"\nxlsx generado: {xlsx} ({os.path.getsize(xlsx) / 1e6:.2f} MB)")

