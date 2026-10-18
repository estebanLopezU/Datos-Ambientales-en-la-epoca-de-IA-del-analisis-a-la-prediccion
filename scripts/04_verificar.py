# -*- coding: utf-8 -*-
"""Verifica la estructura del xlsx generado: hojas, encabezados, formatos y datos."""
import sys
import openpyxl

ruta = sys.argv[1]
wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
print(f"archivo : {ruta}")
print(f"hojas   : {len(wb.sheetnames)} -> {wb.sheetnames}")

for nombre in wb.sheetnames:
    ws = wb[nombre]
    print(f"\n=== {nombre} (max_row={ws.max_row}, max_col={ws.max_column}) ===")
    filas = ws.iter_rows(min_row=1, max_row=min(4, ws.max_row or 1), values_only=False)
    for i, fila in enumerate(filas, start=1):
        celdas = []
        for c in fila[:12]:
            v = "-" if c.value is None else c.value
            coord = getattr(c, "coordinate", "?")
            fmt = getattr(c, "number_format", "General")
            celdas.append(f"{coord}={v!r}[{fmt}]")
        print(f"  fila {i}: " + " | ".join(celdas))

# Comprobaciones de la hoja de datos mas antigua
ws = wb[[n for n in wb.sheetnames if n.isdigit()][0]]
enc = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
print("\nencabezados hoja de datos:", enc)
print("congelados:", ws.freeze_panes, "| autofilter:", ws.auto_filter.ref)

f2 = next(ws.iter_rows(min_row=2, max_row=2, values_only=True))
print("primera fila de datos   :", f2)
assert isinstance(f2[0], object), "la fecha debe ser datetime"
print("tipo de la columna fecha:", type(f2[0]).__name__)
print("\nOK: estructura valida")
