# -*- coding: utf-8 -*-
"""Verifica que el README quede sano: orden, sin duplicados, UTF-8 limpio."""
import io
import sys

p = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal\Excel_Organizado\README.md"
s = io.open(p, encoding="utf-8").read()
lineas = s.split("\n")

fallos = []

# 1. Codificacion
malas = [m for m in ("â€", "Ã¡", "Ã©", "âš", "\ufffd", "\x8f") if m in s]
print("codificacion limpia:", "SI" if not malas else f"NO -> {malas}")
if malas:
    fallos.append("caracteres corruptos")

# 2. Encabezados en orden y sin repetir
enc = [l for l in lineas if l.startswith("## ")]
print("\nsecciones:")
for e in enc:
    print("  " + e)
dup = [e for e in set(enc) if enc.count(e) > 1]
if dup:
    print("  DUPLICADAS:", dup)
    fallos.append("secciones duplicadas")

orden = ["IMPORTANTE: celda vacia", "Por que hay celdas vacias",
         "IMPORTANTE: valores centinela", "Columnas recomendadas",
         "Estructura de cada libro", "Notas al abrir", "Reproducibilidad"]
pos = []
for o in orden:
    idx = [i for i, e in enumerate(enc) if o in e]
    if not idx:
        print(f"  FALTA la seccion: {o}")
        fallos.append(f"falta seccion {o}")
    else:
        pos.append((idx[0], o))
if [x[0] for x in pos] != sorted(x[0] for x in pos):
    print("  Las secciones NO estan en el orden esperado")
    fallos.append("orden de secciones")
else:
    print("\norden de secciones: correcto")

# 3. Tablas bien formadas
print()
n_tablas = 0
i = 0
while i < len(lineas):
    if lineas[i].startswith("|"):
        bloque = []
        while i < len(lineas) and lineas[i].startswith("|"):
            bloque.append(lineas[i])
            i += 1
        n_tablas += 1
        cols = [len(b.split("|")) - 2 for b in bloque]
        if len(set(cols)) != 1:
            print(f"  tabla con columnas irregulares: {bloque[0][:60]}")
            fallos.append("tabla irregular")
        if len(bloque) < 3 or "---" not in bloque[1]:
            print(f"  tabla sin fila separadora: {bloque[0][:60]}")
            fallos.append("tabla sin separador")
    else:
        i += 1
print(f"tablas encontradas: {n_tablas}")

print(f"\nlineas: {len(lineas)} | bytes: {len(s.encode('utf-8'))}")
print("\n" + ("FALLOS: " + ", ".join(fallos) if fallos else "README OK"))
sys.exit(1 if fallos else 0)
