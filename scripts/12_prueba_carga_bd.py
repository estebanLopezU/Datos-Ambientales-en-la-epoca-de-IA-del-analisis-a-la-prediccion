# -*- coding: utf-8 -*-
"""
Prueba de carga de la base de datos local para el volumen del demo.

Pregunta que responde: con datos cada 16 segundos y 2 estaciones, ¿una base
local responde las consultas del dashboard (ultima lectura + serie de 24 h)?

Simula 30 dias de datos con SQLite y mide insercion y consulta reales.
"""
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta

N_ESTACIONES = 2
PERIODO_SEG = 16                      # lo que pide el profesor para el demo
DIAS = 30
VENTANA_H = 24
VARS = ["temperatura", "humedad_relativa", "precipitacion", "presion_barometrica",
        "velocidad_viento", "direccion_viento", "radiacion_solar",
        "evapotranspiracion"]

ruta = os.path.join(tempfile.gettempdir(), "carga_est_campus.db")
if os.path.exists(ruta):
    os.remove(ruta)

con = sqlite3.connect(ruta)
cur = con.cursor()
cur.execute("""
CREATE TABLE lectura (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estacion_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    temperatura REAL, humedad_relativa REAL, precipitacion REAL,
    presion_barometrica REAL, velocidad_viento REAL, direccion_viento REAL,
    radiacion_solar REAL, evapotranspiracion REAL
)""")
cur.execute("CREATE INDEX ix_lec_est_ts ON lectura (estacion_id, timestamp DESC)")
con.commit()

n_por_est = (86400 // PERIODO_SEG) * DIAS
total = n_por_est * N_ESTACIONES
print(f"volumen a simular: {total:,} lecturas "
      f"({n_por_est:,} por estacion x {N_ESTACIONES} estaciones, {DIAS} dias)")
print(f"frecuencia: 1 lectura cada {PERIODO_SEG} s\n")

# --- Insercion ---
t0 = time.time()
base = datetime(2026, 9, 7, 0, 0, 0)
lote = []
for est in (24, 29):
    ts = base
    for i in range(n_por_est):
        lote.append((est, ts.strftime("%Y-%m-%d %H:%M:%S"),
                     18.0 + (i % 60) / 10.0, 80.0 + (i % 17),
                     0.0 if i % 500 else 0.4, 600.0 + (i % 30) / 10.0,
                     1.0 + (i % 40) / 10.0, (i * 7) % 360,
                     300.0 + (i % 200), 0.0))
        ts += timedelta(seconds=PERIODO_SEG)
        if len(lote) >= 5000:
            cur.executemany(
                "INSERT INTO lectura (estacion_id,timestamp,temperatura,"
                "humedad_relativa,precipitacion,presion_barometrica,"
                "velocidad_viento,direccion_viento,radiacion_solar,"
                "evapotranspiracion) VALUES (?,?,?,?,?,?,?,?,?,?)", lote)
            lote = []
    con.commit()
if lote:
    cur.executemany(
        "INSERT INTO lectura (estacion_id,timestamp,temperatura,"
        "humedad_relativa,precipitacion,presion_barometrica,velocidad_viento,"
        "direccion_viento,radiacion_solar,evapotranspiracion) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", lote)
    con.commit()
t_ins = time.time() - t0
print(f"insercion : {t_ins:.1f} s  ({total/t_ins:,.0f} lecturas/s)")

mb = os.path.getsize(ruta) / 1e6
print(f"tamano BD : {mb:.1f} MB")

# --- Consulta 1: ultima lectura de cada estacion (el endpoint "estado actual") ---
n = 200
t0 = time.time()
for _ in range(n):
    cur.execute("""
        SELECT timestamp, temperatura, humedad_relativa, presion_barometrica,
               velocidad_viento, direccion_viento, precipitacion, radiacion_solar
        FROM lectura WHERE estacion_id = 24
        ORDER BY timestamp DESC LIMIT 1""").fetchone()
t_ult = (time.time() - t0) / n * 1000
print(f"\nultima lectura      : {t_ult:.2f} ms  (promedio de {n} consultas)")

# --- Consulta 2: serie de 24 h para la grafica ---
desde = (base + timedelta(days=DIAS - 1)).strftime("%Y-%m-%d %H:%M:%S")
t0 = time.time()
for _ in range(n):
    cur.execute("""
        SELECT timestamp, temperatura, humedad_relativa, precipitacion
        FROM lectura WHERE estacion_id = 24 AND timestamp >= ?
        ORDER BY timestamp ASC""", (desde,)).fetchall()
t_ser = (time.time() - t0) / n * 1000
filas = len(cur.execute("""
        SELECT timestamp FROM lectura WHERE estacion_id = 24 AND timestamp >= ?
        ORDER BY timestamp ASC""", (desde,)).fetchall())
print(f"serie de {VENTANA_H} h      : {t_ser:.2f} ms  ({filas:,} puntos por grafica)")

# --- Consulta 3: agregado horario (para no mandar 5.400 puntos al navegador) ---
t0 = time.time()
for _ in range(50):
    cur.execute("""
        SELECT substr(timestamp,1,13) AS hora,
               AVG(temperatura), MIN(temperatura), MAX(temperatura),
               AVG(humedad_relativa), SUM(precipitacion), AVG(presion_barometrica)
        FROM lectura WHERE estacion_id = 24 AND timestamp >= ?
        GROUP BY hora ORDER BY hora ASC""", (desde,)).fetchall()
t_agg = (time.time() - t0) / 50 * 1000
print(f"agregado horario    : {t_agg:.2f} ms  (24 puntos por grafica)")

# --- Consulta 4: escrito concurrente mientras se lee (endpoint recibiendo) ---
t0 = time.time()
for i in range(500):
    cur.execute("INSERT INTO lectura (estacion_id,timestamp,temperatura,"
                "humedad_relativa,precipitacion,presion_barometrica,"
                "velocidad_viento,direccion_viento,radiacion_solar,"
                "evapotranspiracion) VALUES (24,?,?,?,?,?,?,?,?,?)",
                ((base + timedelta(days=DIAS, seconds=i * PERIODO_SEG))
                 .strftime("%Y-%m-%d %H:%M:%S"), 18.0, 80.0, 0.0, 600.0, 1.0, 90, 300.0, 0.0))
    cur.execute("SELECT temperatura FROM lectura WHERE estacion_id=24 "
                "ORDER BY timestamp DESC LIMIT 1").fetchone()
con.commit()
t_mix = time.time() - t0
print(f"\n500 inserciones + 500 lecturas intercaladas: {t_mix:.2f} s "
      f"({t_mix/500*1000:.2f} ms por ciclo escribir+leer)")

con.close()
os.remove(ruta)
print("\nCONCLUSION:")
print(f"  - {total:,} lecturas en {DIAS} dias ocupan ~{mb:.0f} MB: trivial para SQLite.")
print(f"  - El dashboard responde en milisegundos: no hace falta PostgreSQL.")
print(f"  - Para la grafica conviene agregar: {filas:,} puntos en bruto vs 24 por hora.")
