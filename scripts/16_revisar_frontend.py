# -*- coding: utf-8 -*-
"""
Verifica la sintaxis del JavaScript del dashboard con Node si esta disponible,
y valida que los archivos estaticos y las plantillas existan.
"""
import json
import os
import re
import shutil
import subprocess
import sys

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
JS = os.path.join(BASE, "estaciones", "static", "js", "dashboard.js")
CSS = os.path.join(BASE, "estaciones", "static", "css", "dashboard.css")
HTML = os.path.join(BASE, "estaciones", "templates", "dashboard.html")

fallos = []

# --- 1. Sintaxis del JS: node es la autoridad; sin node, balance aproximado ---
src = open(JS, encoding="utf-8").read()

node = shutil.which("node")
if node:
    r = subprocess.run([node, "--check", JS], capture_output=True, text=True)
    if r.returncode == 0:
        print("sintaxis JS        : OK (node --check es la autoridad)")
    else:
        print("sintaxis JS        : FALLA")
        print(r.stderr.strip()[:800])
        fallos.append("sintaxis JS")
else:
    # Sin node, el conteo de balance es una red de seguridad aproximada.
    limpio = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    limpio = re.sub(r"//[^\n]*", "", limpio)
    limpio = re.sub(r"\$\{[^{}]*\}", "PLACEHOLDER", limpio)
    limpio = re.sub(r"'(\\.|[^'\\])*'", "''", limpio)
    limpio = re.sub(r'"(\\.|[^"\\])*"', '""', limpio)
    limpio = re.sub(r"`(\\.|[^`\\])*`", "``", limpio)
    for abre, cierra, nombre in (("{", "}", "llaves"),
                                 ("(", ")", "parentesis"),
                                 ("[", "]", "corchetes")):
        na, nc = limpio.count(abre), limpio.count(cierra)
        if na != nc:
            print(f"balance de {nombre:<11}: FALLA ({na} vs {nc})")
            fallos.append(f"balance {nombre}")
        else:
            print(f"balance de {nombre:<11}: OK ({na} pares)")

# --- 3. Existen los archivos y no estan vacios ---
for etiqueta, ruta in (("JS", JS), ("CSS", CSS), ("HTML", HTML)):
    if not os.path.isfile(ruta):
        print(f"{etiqueta:<4} existe        : FALLA ({ruta})")
        fallos.append(f"falta {etiqueta}")
    else:
        kb = os.path.getsize(ruta) / 1024
        print(f"{etiqueta:<4} existe        : OK ({kb:.1f} KB)")

# --- 4. La plantilla referencia los estaticos que existen ---
html = open(HTML, encoding="utf-8").read()
for ref in re.findall(r"\{% static '([^']+)' %\}", html):
    destino = os.path.join(BASE, "estaciones", "static", ref.replace("/", os.sep))
    ok = os.path.isfile(destino)
    print(f"  static referido : {'OK  ' if ok else 'FALLA'} {ref}")
    if not ok:
        fallos.append(f"static faltante {ref}")

# --- 5. Los bloques de Django quedan balanceados ---
for etiqueta, patron in (("for/endfor", r"\{%\s*for\b"),
                         ("if/endif", r"\{%\s*if\b")):
    n_abre = len(re.findall(patron, html))
    cierra = "endfor" if "for" in etiqueta else "endif"
    n_cierra = len(re.findall(r"\{%\s*" + cierra + r"\s*%\}", html))
    if n_abre != n_cierra:
        print(f"  {etiqueta:<12}   : FALLA ({n_abre} vs {n_cierra})")
        fallos.append(etiqueta)
    else:
        print(f"  {etiqueta:<12}   : OK ({n_abre})")

print()
if fallos:
    print("FALLOS:", ", ".join(fallos))
    sys.exit(1)
print("TODO OK")
