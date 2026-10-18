# -*- coding: utf-8 -*-
"""
Crea db_vercel.sqlite3: una copia ligera de db.sqlite3 para el deploy en Vercel.

El bundle de Vercel tiene un limite de 500 MB sin comprimir y db.sqlite3
pesa ~1.1 GB (4.8 millones de lecturas desde 2002), asi que esta copia
usa dos niveles de resolucion para que EL RANGO COMPLETO 2002-2026 se vea
en la demo:

  * ultimos N dias (por defecto 90): crudos, tal cual.
  * todo lo anterior (2002 -> hoy-N): UNA lectura por hora y estacion
    (la primera fila real de esa hora). ~420k filas en vez de 4.7
    millones: el dashboard muestra toda la serie historica.

El resto de las tablas (estaciones, consolas, usuarios...) van completas.

Uso:
    python scripts/crear_db_vercel.py [dias_crudos]

Salida: db_vercel.sqlite3 en la raiz del proyecto (sube a Vercel, NO a git).
"""
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "db.sqlite3")
DST = os.path.join(BASE, "db_vercel.sqlite3")

# Tablas que se copian COMPLETAS (todo menos lecturas historicas).
# estaciones_lectura: crudo reciente + historico muestreado por hora.
DIAS = int(sys.argv[1]) if len(sys.argv) > 1 else 90


def main():
    if not os.path.exists(SRC):
        sys.exit("no existe db.sqlite3")
    t0 = time.time()
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    cur = src.cursor()

    tablas = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    n_total = cur.execute("SELECT COUNT(*) FROM estaciones_lectura").fetchone()[0]
    mn, mx = cur.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM estaciones_lectura").fetchone()
    print(f"origen: {os.path.getsize(SRC)/1e6:.0f} MB | "
          f"lecturas={n_total} ({mn} .. {mx}) | tablas={len(tablas)}")

    if os.path.exists(DST):
        os.remove(DST)
    # Solo LA conexion de escritura lleva el ATTACH. Las demas conexiones
    # leen el origen directamente por su ruta (con ATTACH en cada conexion
    # la escritura cruzada no garantiza nada).
    lector_src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    c_src = lector_src.cursor()
    dst = sqlite3.connect(DST)
    dst.execute("PRAGMA journal_mode=OFF")
    dst.execute("PRAGMA synchronous=OFF")
    dst.execute("ATTACH DATABASE ? AS src", (SRC,))

    # 1) esquema identico (tablas + indices + triggers)
    esquema = ";\n".join(
        sql for (sql,) in cur.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%'")) + ";"
    dst.executescript(esquema)

    # 2) datos (el corte usa el mismo formato UTC que Django en sqlite:
    #    'YYYY-MM-DD HH:MM:SS' con espacio, para que la comparacion de
    #    cadenas del timestamp ISO funcione igual que la de SQLite).
    muestra = cur.execute(
        "SELECT timestamp FROM estaciones_lectura LIMIT 1").fetchone()
    print(f"muestra timestamp: {muestra[0]!r}")
    corte = (datetime.now(timezone.utc) - timedelta(days=DIAS)
             ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"corte crudo: timestamp >= {corte!r}")
    print(f"muestra de como se ve el rango historico: "
          f"{[r[0] for r in cur.execute('SELECT substr(timestamp,1,13) FROM estaciones_lectura LIMIT 3')]}")
    n_pre = cur.execute(
        "SELECT COUNT(*) FROM estaciones_lectura WHERE timestamp < ?",
        (corte,)).fetchone()[0]
    print(f"lecturas historicas a muestrear: {n_pre}")
    for tabla in tablas:
        if tabla == "estaciones_lectura":
            # a) crudo: los ultimos N dias, resolucion total
            n_crudo = dst.execute(
                "INSERT INTO estaciones_lectura SELECT * FROM src.estaciones_lectura "
                "WHERE timestamp >= ?", (corte,)).rowcount
            print(f"  crudo insertado: {n_crudo}")
            # b) historico 2002->corte: UNA fila real por hora y estacion.
            #    Primero se calculan los id en UNA fotografia (la conexion
            #    destino sola no alcanza: cualquier otra lectura cruzada la
            #    vacia), y luego se insertan solo esos id.
            ids = [r[0] for r in c_src.execute(
                "SELECT MIN(id) FROM estaciones_lectura"
                " WHERE timestamp < ?"
                " GROUP BY estacion_id, substr(timestamp, 1, 13)",
                (corte,))]
            print(f"  id historicos calculados: {len(ids)} "
                  f"(muestra: {ids[:3]})")
            n_hist = 0
            CHUNK = 500
            for i in range(0, len(ids), CHUNK):
                bloque = ids[i:i + CHUNK]
                n_hist += dst.execute(
                    "INSERT INTO estaciones_lectura SELECT * FROM src.estaciones_lectura"
                    " WHERE id IN (%s)" % ",".join("?" * len(bloque)),
                    bloque).rowcount
                dst.commit()
            print(f"  {tabla}: {n_crudo} crudos (>= {DIAS} d) + "
                  f"{n_hist} historicas horarias")
        else:
            n = dst.execute(
                f"INSERT INTO {tabla} SELECT * FROM src.{tabla}").rowcount
            print(f"  {tabla}: {n} filas")
    src.close()
    lector_src.close()

    dst.execute("ANALYZE")
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    mb = os.path.getsize(DST) / 1e6
    chk = sqlite3.connect(DST)
    mn2, mx2, n2 = chk.execute(
        "SELECT MIN(timestamp), MAX(timestamp), COUNT(*) "
        "FROM estaciones_lectura").fetchone()
    chk.close()
    print(f"db_vercel.sqlite3 listo: {mb:.1f} MB | "
          f"lecturas={n2} ({mn2} .. {mx2}) | {time.time()-t0:.1f} s")
    if mb > 450:
        print("AVISO: >450 MB, baja los dias crudos: "
              "python scripts/crear_db_vercel.py 30")


if __name__ == "__main__":
    main()
