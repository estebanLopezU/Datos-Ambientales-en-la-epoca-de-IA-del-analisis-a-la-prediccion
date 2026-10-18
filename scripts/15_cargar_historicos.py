# -*- coding: utf-8 -*-
"""Carga los historicos y verifica el resultado. Evita el escapado de PowerShell."""
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


rc = run(["manage.py", "cargar_historicos"], "CARGAR HISTORICOS")

# Resumen de lo que quedo en la base.
codigo = r'''
import django, os, sys
sys.path.insert(0, r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "est_campus.settings")
django.setup()
from estaciones.models import Estacion, Lectura
from django.utils import timezone
print("RESUMEN DE LA BASE")
for e in Estacion.objects.order_by("codigo"):
    qs = Lectura.objects.filter(estacion=e)
    primera = qs.order_by("timestamp").first()
    ultima = qs.order_by("-timestamp").first()
    print(f"  {e.codigo} {e.nombre}: {qs.count():,} lecturas")
    if primera and ultima:
        print(f"      desde {timezone.localtime(primera.timestamp)}")
        print(f"      hasta {timezone.localtime(ultima.timestamp)}")
'''
run(["-c", codigo], "CONTENIDO DE db.sqlite3")
sys.exit(rc)
