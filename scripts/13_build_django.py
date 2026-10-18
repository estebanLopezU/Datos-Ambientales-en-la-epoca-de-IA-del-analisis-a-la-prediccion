# -*- coding: utf-8 -*-
"""
Ejecuta makemigrations y migrate en el entorno virtual.

Evita los problemas de escapado de PowerShell con rutas largas.
"""
import os
import subprocess
import sys

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
PY = r"C:\Users\esteb\entornos_venv\est_campus\Scripts\python.exe"


def run(args, titulo):
    print("=" * 70)
    print(titulo)
    print("=" * 70)
    r = subprocess.run([PY] + args, cwd=BASE, capture_output=True, text=True)
    salida = (r.stdout or "") + (r.stderr or "")
    print(salida.rstrip())
    print(f"[exit {r.returncode}]\n")
    return r.returncode


rc = 0
rc |= run(["manage.py", "makemigrations", "estaciones"], "MAKEMIGRATIONS")
rc |= run(["manage.py", "migrate"], "MIGRATE")

# Comprueba que el proyecto arranca (check detecta errores de configuracion).
rc |= run(["manage.py", "check"], "CHECK DE CONFIGURACION")

sys.exit(rc)
