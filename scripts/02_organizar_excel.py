# -*- coding: utf-8 -*-
"""
Organiza los CSV de las estaciones UNAL-Manizales en libros de Excel bien formados.

Diseno:
  * Un libro .xlsx por estacion.
  * "Portada"        -> metadata, estructura y advertencias.
  * "Resumen_Anual"  -> por ano: registros, dias, medias, acumulados, % faltantes.
  * "Calidad_Datos"  -> completitud, rangos y valores fuera de rango (centinelas).
  * "2004".."2026"   -> datos crudos, una hoja por ano (Excel limita a 1.048.576 filas).

Escritura en modo streaming (constant_memory) para no agotar la RAM.
"""
import os
import time
import numpy as np
import pandas as pd
import xlsxwriter

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
DATOS = os.path.join(BASE, "Est_Datos")
SALIDA = os.path.join(BASE, "Excel_Organizado")
LIMITE_FILAS_EXCEL = 1_048_576
CHUNK = 300_000

ESTACIONES = [
    {"codigo": "24", "nombre": "La Nubia",
     "csv": os.path.join(DATOS, "24-La Nubia.csv"),
     "xlsx": os.path.join(SALIDA, "Estacion_24_La_Nubia.xlsx")},
    {"codigo": "29", "nombre": "Palogrande-Postgrados",
     "csv": os.path.join(DATOS, "29-Palogrande-Postgrados.csv"),
     "xlsx": os.path.join(SALIDA, "Estacion_29_Palogrande_Postgrados.xlsx")},
]

# 'brillo' se excluye de las hojas de datos: esta 100% vacia en ambas estaciones.
VARS = ["precipitacion", "temperatura", "humedad_relativa", "nivel", "caudal",
        "velocidad_viento", "direccion_viento", "presion_barometrica",
        "evapotranspiracion", "radiacion_solar"]
TODAS_VARS = VARS + ["brillo"]

ETIQUETAS = {
    "precipitacion": "Precipitacion (mm)",
    "temperatura": "Temperatura (C)",
    "humedad_relativa": "Humedad rel. (%)",
    "nivel": "Nivel",
    "caudal": "Caudal",
    "velocidad_viento": "Vel. viento (m/s)",
    "direccion_viento": "Dir. viento (grados)",
    "presion_barometrica": "Presion (hPa)",
    "evapotranspiracion": "Evapotranspiracion (mm)",
    "radiacion_solar": "Radiacion solar (W/m2)",
    "brillo": "Brillo",
}

# Rango fisicamente plausible. Fuera de esto => centinela o falla de sensor.
LIMITES = {
    "precipitacion": (0.0, 200.0),
    "temperatura": (-10.0, 50.0),
    "humedad_relativa": (0.0, 100.0),
    "nivel": (0.0, 100.0),
    "caudal": (0.0, 100000.0),
    "velocidad_viento": (0.0, 60.0),
    "direccion_viento": (0.0, 360.0),
    "presion_barometrica": (400.0, 900.0),
    "evapotranspiracion": (0.0, 100.0),
    "radiacion_solar": (0.0, 1500.0),
    "brillo": (0.0, 200000.0),
}

FORMATOS = {
    "precipitacion": "0.0", "temperatura": "0.00", "humedad_relativa": "0",
    "nivel": "0.000", "caudal": "0.000", "velocidad_viento": "0.00",
    "direccion_viento": "0", "presion_barometrica": "0.00",
    "evapotranspiracion": "0.00", "radiacion_solar": "0.0",
}

OBSERVACION = {
    "brillo": "Vacia al 100%: excluida del libro.",
    "nivel": "Constante 0: sin informacion util.",
    "caudal": "Constante 0: sin informacion util.",
    "humedad_relativa": "255 % es centinela de error del sensor.",
    "velocidad_viento": "113.99 es fisicamente imposible (centinela).",
    "direccion_viento": "Valores > 360 grados son invalidos.",
    "presion_barometrica": "0 hPa es invalido (centinela).",
    "evapotranspiracion": "999.99 es centinela de error.",
    "radiacion_solar": "Muy por encima de la radiacion teorica: revisar calibracion.",
    "temperatura": "Rangos coherentes con el clima de Manizales.",
    "precipitacion": "Rangos coherentes; verificar eventos extremos.",
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# PASADA 1: metricas agregadas (bajo consumo de memoria)
# ---------------------------------------------------------------------------
def calcular_metricas(csv_path):
    total = 0
    ordenado = True
    partes = []
    # Fechas unicas por ano. Se usa un conjunto y no la suma de nunique() por
    # chunk, porque un dia partido entre dos chunks se contaria dos veces.
    fechas_por_anio = {}

    for chunk in pd.read_csv(csv_path, chunksize=CHUNK, dtype=str,
                             keep_default_na=True, na_values=[""]):
        total += len(chunk)
        fecha = pd.to_datetime(chunk["fecha"], format="%Y-%m-%d", errors="coerce")
        if fecha.notna().any() and not fecha.dropna().is_monotonic_increasing:
            ordenado = False

        c = chunk.copy()
        c["anio"] = fecha.dt.year
        for v in TODAS_VARS:
            c[v] = pd.to_numeric(c[v], errors="coerce")

        for anio, grupo in c.groupby("anio")["fecha"]:
            if pd.isna(anio):
                continue
            s = fechas_por_anio.setdefault(int(anio), set())
            s.update(grupo.dropna().unique())

        g = c.groupby("anio")
        partes.append({
            "n": g.size(),
            "sum": g[TODAS_VARS].sum(min_count=1),
            "cnt": g[TODAS_VARS].count(),
            "min": g[TODAS_VARS].min(),
            "max": g[TODAS_VARS].max(),
        })
        log(f"  ... pasada 1: {total:,} filas acumuladas")

    if not partes:
        raise RuntimeError("El CSV no devolvio filas.")

    # Se agrega cada metrica por ano antes de combinar, para que el indice
    # resultante sea unico (Index.union() conserva duplicados si no lo es).
    registros = pd.concat([p["n"] for p in partes]).groupby(level=0).sum()
    suma = pd.concat([p["sum"] for p in partes]).groupby(level=0).sum(min_count=1)
    conteo = pd.concat([p["cnt"] for p in partes]).groupby(level=0).sum(min_count=1)
    minimo = pd.concat([p["min"] for p in partes]).groupby(level=0).min()
    maximo = pd.concat([p["max"] for p in partes]).groupby(level=0).max()

    idx = (registros.index.union(conteo.index)
           .unique()
           .sort_values())

    resumen = pd.DataFrame(index=idx)
    resumen["registros"] = registros
    resumen["dias"] = [len(fechas_por_anio.get(int(a), ())) for a in idx]

    return {"total": total, "ordenado": ordenado, "resumen": resumen,
            "suma": suma.reindex(idx), "conteo": conteo.reindex(idx),
            "minimo": minimo.reindex(idx), "maximo": maximo.reindex(idx)}


def contar_fuera_de_rango(csv_path):
    sospechosos = {v: 0 for v in TODAS_VARS}
    for chunk in pd.read_csv(csv_path, chunksize=CHUNK, dtype=str,
                             keep_default_na=True, na_values=[""]):
        num = chunk[TODAS_VARS].apply(pd.to_numeric, errors="coerce")
        for v in TODAS_VARS:
            lo, hi = LIMITES[v]
            s = num[v]
            sospechosos[v] += int(((s < lo) | (s > hi)).sum())
    return sospechosos


# ---------------------------------------------------------------------------
# PASADA 2: hojas de datos, una por ano
# ---------------------------------------------------------------------------
def escribir_datos(csv_path, wb, fmts):
    ws = None
    anio_actual = None
    fila = 1
    filas_hoja = 0
    hojas = []
    total_escrito = 0

    for chunk in pd.read_csv(csv_path, chunksize=CHUNK, dtype=str,
                             keep_default_na=True, na_values=[""]):
        fecha = pd.to_datetime(chunk["fecha"] + " " + chunk["tiempo"],
                               format="%Y-%m-%d %H:%M:%S", errors="coerce")
        anios = fecha.dt.year

        # Un bloque puede cruzar el 31/12: se parte en tramos de un mismo ano.
        cortes = np.flatnonzero(anios.values[1:] != anios.values[:-1]) + 1
        for pos in np.split(np.arange(len(chunk)), cortes):
            if len(pos) == 0:
                continue
            anio = anios.iloc[pos[0]]
            if pd.isna(anio):
                continue
            anio = int(anio)

            if anio != anio_actual or ws is None:
                if ws is not None:
                    ws.autofilter(0, 0, fila - 1, len(VARS))
                    log(f"    hoja {anio_actual}: {filas_hoja:,} filas")
                if filas_hoja + 1 > LIMITE_FILAS_EXCEL:
                    raise RuntimeError("Se excede el limite de filas de Excel")
                ws = wb.add_worksheet(str(anio))
                ws.freeze_panes(1, 1)
                ws.set_row(0, 30, fmts["hdr"])
                for j, h in enumerate(["Fecha y hora"] + [ETIQUETAS[v] for v in VARS]):
                    ws.write(0, j, h, fmts["hdr"])
                ws.set_column(0, 0, 19, fmts["fecha"])
                for j, v in enumerate(VARS, start=1):
                    ws.set_column(j, j, 17, fmts[v])
                hojas.append(str(anio))
                anio_actual = anio
                fila = 1
                filas_hoja = 0

            fechas = fecha.iloc[pos].tolist()
            matriz = chunk[VARS].iloc[pos].apply(pd.to_numeric, errors="coerce")
            matriz = matriz.astype(object).where(matriz.notna(), None).to_numpy()

            for k in range(len(pos)):
                r = fila + k
                ws.write_datetime(r, 0, fechas[k], fmts["fecha"])
                ws.write_row(r, 1, matriz[k].tolist())
            fila += len(pos)
            filas_hoja += len(pos)
            total_escrito += len(pos)
        log(f"  ... pasada 2: {total_escrito:,} filas escritas")

    if ws is not None:
        ws.autofilter(0, 0, fila - 1, len(VARS))
        log(f"    hoja {anio_actual}: {filas_hoja:,} filas")
    return hojas, total_escrito


# ---------------------------------------------------------------------------
# HOJAS INFORMATIVAS
# ---------------------------------------------------------------------------
def num(ws, fila, col, valor, fmt=None):
    """Escribe un numero; si es None/NaN deja la celda vacia en lugar de fallar.

    Rechaza explicitamente valores no escalares: un bug de agregacion que
    devuelva una Serie debe fallar ruidosamente, no escribir celdas vacias.
    """
    # numpy.int64/float64 son escalares pero tambien tienen .ndim (== 0);
    # una Serie tiene ndim == 1. Se rechaza solo lo que no sea escalar.
    if isinstance(valor, (list, tuple, set, dict)):
        raise TypeError(f"Se esperaba un escalar en ({fila}, {col}); se recibio {type(valor).__name__}")
    if getattr(valor, "ndim", 0) != 0:
        raise TypeError(f"Se esperaba un escalar en ({fila}, {col}); se recibio {type(valor).__name__} con ndim={valor.ndim}")
    if valor is None:
        ws.write_blank(fila, col, None, fmt)
        return
    try:
        v = float(valor)
    except (TypeError, ValueError):
        ws.write_blank(fila, col, None, fmt)
        return
    if not np.isfinite(v):
        ws.write_blank(fila, col, None, fmt)
        return
    ws.write_number(fila, col, v, fmt)


def escribir_resumen(m, wb, fmts):
    ws = wb.add_worksheet("Resumen_Anual")
    ws.set_row(0, 34, fmts["hdr"])
    ws.freeze_panes(1, 1)

    encabezados = ["Ano", "Registros", "Dias con datos", "Temp. media (C)",
                   "Temp. min (C)", "Temp. max (C)", "Precip. acumulada (mm)",
                   "Humedad media (%)", "Viento medio (m/s)",
                   "Radiacion media (W/m2)", "Datos faltantes (%)"]
    for j, h in enumerate(encabezados):
        ws.write(0, j, h, fmts["hdr"])
    ws.set_column(0, 0, 8, fmts["int"])
    ws.set_column(1, 2, 16, fmts["int"])
    ws.set_column(3, 5, 15, fmts["num2"])
    ws.set_column(6, 6, 21, fmts["num1"])
    ws.set_column(7, 7, 16, fmts["num1"])
    ws.set_column(8, 9, 19, fmts["num2"])
    ws.set_column(10, 10, 18, fmts["pct"])

    suma, conteo = m["suma"], m["conteo"]

    def media(v, anio):
        cnt = conteo[v].get(anio, np.nan)
        if not np.isfinite(cnt) or cnt == 0:
            return None
        return float(suma[v].get(anio, np.nan) / cnt)

    for i, anio in enumerate(m["resumen"].index, start=1):
        anio = int(anio)
        num(ws, i, 0, anio)
        num(ws, i, 1, m["resumen"]["registros"].loc[anio])
        num(ws, i, 2, m["resumen"]["dias"].loc[anio])
        num(ws, i, 3, media("temperatura", anio), fmts["num2"])
        num(ws, i, 4, m["minimo"]["temperatura"].get(anio, np.nan), fmts["num2"])
        num(ws, i, 5, m["maximo"]["temperatura"].get(anio, np.nan), fmts["num2"])
        num(ws, i, 6, suma["precipitacion"].get(anio, np.nan), fmts["num1"])
        num(ws, i, 7, media("humedad_relativa", anio), fmts["num1"])
        num(ws, i, 8, media("velocidad_viento", anio), fmts["num2"])
        num(ws, i, 9, media("radiacion_solar", anio), fmts["num1"])

        celdas = float(conteo.loc[anio, VARS].sum())
        n = float(m["resumen"]["registros"].loc[anio]) * len(VARS)
        num(ws, i, 10, (100.0 * (1 - celdas / n)) if n else None, fmts["pct"])

    ws.autofilter(0, 0, len(m["resumen"].index), len(encabezados) - 1)
    return ws


def escribir_calidad(m, sospechosos, wb, fmts):
    ws = wb.add_worksheet("Calidad_Datos")
    ws.set_row(0, 34, fmts["hdr"])
    encabezados = ["Variable", "Registros con dato", "Completitud (%)", "Minimo",
                   "Maximo", "Valores fuera de rango", "Rango valido", "Observacion"]
    for j, h in enumerate(encabezados):
        ws.write(0, j, h, fmts["hdr"])
    ws.set_column(0, 0, 24)
    ws.set_column(1, 2, 19, fmts["int"])
    ws.set_column(3, 4, 14, fmts["num2"])
    ws.set_column(5, 5, 21, fmts["int"])
    ws.set_column(6, 6, 16)
    ws.set_column(7, 7, 56)

    r = 1
    for v in TODAS_VARS:
        cnt = float(m["conteo"][v].sum())
        ws.write(r, 0, ETIQUETAS[v])
        num(ws, r, 1, cnt, fmts["int"])
        num(ws, r, 2, (100.0 * cnt / m["total"]) if m["total"] else None, fmts["pct"])
        if cnt > 0:
            num(ws, r, 3, m["minimo"][v].min(), fmts["num2"])
            num(ws, r, 4, m["maximo"][v].max(), fmts["num2"])
        else:
            ws.write(r, 3, "-")
            ws.write(r, 4, "-")
        num(ws, r, 5, sospechosos[v], fmts["int"])
        lo, hi = LIMITES[v]
        ws.write(r, 6, f"{lo:g} a {hi:g}")
        ws.write(r, 7, OBSERVACION.get(v, ""))
        r += 1
    ws.autofilter(0, 0, r - 1, len(encabezados) - 1)
    return ws


def escribir_portada(est, m, hojas, escrito, generado, wb, fmts):
    ws = wb.add_worksheet("Portada")
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 74)
    ws.hide_gridlines(2)
    ws.hide_gridlines(2)
    ws.set_row(0, 36)

    ws.merge_range(0, 0, 0, 1, f"Estacion {est['codigo']} - {est['nombre']}", fmts["titulo"])
    r = 2

    def par(etiqueta, valor):
        nonlocal r
        ws.write(r, 0, etiqueta, fmts["clave"])
        ws.write(r, 1, valor)
        r += 1

    par("Fuente", os.path.basename(est["csv"]))
    par("Red", "Estaciones automaticas - Universidad Nacional de Colombia, sede Manizales")
    par("Generado", generado)
    par("Registros en el CSV", f"{m['total']:,}")
    par("Registros escritos", f"{escrito:,}")
    par("Periodo", f"{int(m['resumen'].index.min())} - {int(m['resumen'].index.max())}")
    par("Frecuencia original", "5 minutos (irregular en el tramo mas reciente)")
    par("Hojas de datos", f"{len(hojas)} (una por ano: {', '.join(hojas)})")

    r += 1
    ws.write(r, 0, "Estructura del libro", fmts["clave"])
    r += 1
    for t in ["Portada: esta hoja (metadata y advertencias).",
              "Resumen_Anual: estadisticas agregadas por ano.",
              "Calidad_Datos: completitud, rangos y valores sospechosos.",
              "2004 ... 2026: datos crudos, una hoja por ano, con filtros y encabezado fijo."]:
        ws.write(r, 1, t)
        r += 1

    r += 1
    ws.write(r, 0, "Advertencias", fmts["clave"])
    r += 1
    notas = [
        "Columna 'brillo' omitida: esta vacia al 100% en el archivo original.",
        "'nivel' y 'caudal' son constantes e iguales a 0: no aportan informacion.",
        "Las celdas vacias son datos ausentes; NO se rellenaron con ceros.",
        "Se detectaron valores centinela / errores de sensor (ver Calidad_Datos):",
        "    humedad_relativa hasta 255 %, velocidad_viento hasta 113.99,",
        "    direccion_viento hasta 507 grados, presion_barometrica 0 hPa,",
        "    evapotranspiracion hasta 999.99, radiacion_solar hasta 9818.",
        "Los valores originales se conservan intactos: filtre antes de analizar.",
        "Unidades inferidas de la nomenclatura estandar; conviene confirmarlas con",
        "    la ficha tecnica de la estacion antes de publicar cifras.",
    ]
    for n in notas:
        ws.write(r, 1, n)
        r += 1


def construir_formatos(wb):
    f = {}
    f["titulo"] = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F3864",
                                 "align": "left", "valign": "vcenter"})
    f["hdr"] = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F3864",
                              "align": "center", "valign": "vcenter", "text_wrap": True,
                              "border": 1, "border_color": "#8EA9DB"})
    f["clave"] = wb.add_format({"bold": True, "valign": "top", "font_color": "#1F3864"})
    f["fecha"] = wb.add_format({"num_format": "yyyy-mm-dd hh:mm", "align": "center"})
    f["int"] = wb.add_format({"num_format": "#,##0"})
    f["num1"] = wb.add_format({"num_format": "#,##0.0"})
    f["num2"] = wb.add_format({"num_format": "#,##0.00"})
    f["pct"] = wb.add_format({"num_format": '0.0"%"'})
    for v in VARS:
        f[v] = wb.add_format({"num_format": FORMATOS[v], "align": "right"})
    return f


# ---------------------------------------------------------------------------
def main():
    os.makedirs(SALIDA, exist_ok=True)
    generado = time.strftime("%Y-%m-%d %H:%M:%S")
    resultado = []

    for est in ESTACIONES:
        log("=" * 72)
        log(f"ESTACION {est['codigo']} - {est['nombre']}")
        log("=" * 72)
        t0 = time.time()

        log("Pasada 1/3: metricas de resumen y calidad...")
        m = calcular_metricas(est["csv"])
        sospechosos = contar_fuera_de_rango(est["csv"])
        if not m["ordenado"]:
            log("  AVISO: el CSV no esta ordenado por fecha; revisar hojas por ano.")

        log("Pasada 2/3: escribiendo el libro de Excel...")
        wb = xlsxwriter.Workbook(est["xlsx"], {
            "constant_memory": True,
            "default_date_format": "yyyy-mm-dd hh:mm",
            "remove_timezone": True,
        })
        wb.set_properties({
            "title": f"Estacion {est['codigo']} - {est['nombre']}",
            "subject": "Datos meteorologicos cada 5 minutos",
            "author": "Script de organizacion de datos UNAL",
            "comments": "Generado desde el CSV original sin alterar valores.",
        })
        fmts = construir_formatos(wb)

        # En modo streaming las hojas se escriben en orden y no se puede volver
        # atras, asi que las informativas se crean primero. Los nombres de las
        # hojas de datos ya se conocen: son los anos del resumen.
        hojas = [str(int(a)) for a in m["resumen"].index]
        esperado = int(m["resumen"]["registros"].sum())
        escribir_portada(est, m, hojas, esperado, generado, wb, fmts)
        escribir_resumen(m, wb, fmts)
        escribir_calidad(m, sospechosos, wb, fmts)
        hojas, escrito = escribir_datos(est["csv"], wb, fmts)
        wb.close()

        mb = os.path.getsize(est["xlsx"]) / 1e6
        log(f"Listo: {est['xlsx']}")
        log(f"  hojas: {len(hojas) + 3} | filas: {escrito:,}/{m['total']:,} | "
            f"{mb:.1f} MB | {time.time() - t0:.0f} s")
        if escrito != esperado:
            log(f"  AVISO: se escribieron {escrito:,} filas y se esperaban {esperado:,}")
        resultado.append((est["codigo"], len(hojas) + 3, escrito, m["total"], mb))

    log("=" * 72)
    log("RESUMEN FINAL")
    for cod, nh, esc, tot, mb in resultado:
        log(f"  Estacion {cod}: {nh} hojas, {esc:,}/{tot:,} filas, {mb:.1f} MB")
    log(f"Carpeta de salida: {SALIDA}")


if __name__ == "__main__":
    main()
