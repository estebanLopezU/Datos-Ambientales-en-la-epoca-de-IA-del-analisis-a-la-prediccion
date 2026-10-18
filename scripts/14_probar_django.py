# -*- coding: utf-8 -*-
"""Ejecuta los chequeos y pruebas de Django. Evita el escapado de PowerShell."""
import subprocess
import sys

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
PY = r"C:\Users\esteb\entornos_venv\est_campus\Scripts\python.exe"


def run(args, titulo):
    print("=" * 70)
    print(titulo)
    print("=" * 70)
    r = subprocess.run([PY] + args, cwd=BASE, capture_output=True, text=True)
    print(((r.stdout or "") + (r.stderr or "")).rstrip())
    print(f"[exit {r.returncode}]\n")
    return r.returncode


rc = run(["manage.py", "check"], "CHECK")
rc |= run(["manage.py", "test", "estaciones", "-v", "2"], "PRUEBAS")
sys.exit(rc)
