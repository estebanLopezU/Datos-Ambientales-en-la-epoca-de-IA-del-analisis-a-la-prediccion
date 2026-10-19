# -*- coding: utf-8 -*-
"""Descarga el respaldo historico del Release con progreso y reintentos.

Uso:  python scripts/descargar_respaldo.py
Salida: tmp/db_historico_2002_2026.zip (omite si ya existe y coincide en tamano).
"""
import os
import sys
import time
import urllib.request

URL = ("https://github.com/estebanLopezU/"
       "Datos-Ambientales-en-la-epoca-de-IA-del-analisis-a-la-prediccion"
       "/releases/download/respaldo-db-2002-2026/db_historico_2002_2026.zip")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(BASE, "tmp", "db_historico_2002_2026.zip")


def _tamano_remoto(req_abrir):
    try:
        with req_abrir(URL) as r:
            n = r.headers.get("Content-Length")
            return int(n) if n else None
    except Exception as e:
        print(f"no se pudo consultar tamano remoto: {e}")
        return None


def main():
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    esperado = _tamano_remoto(urllib.request.urlopen)
    if os.path.exists(DST):
        local = os.path.getsize(DST)
        print(f"local: {local:,} bytes | remoto: {esperado if esperado else '?'} bytes")
        if esperado and local == esperado:
            print("ya descargado y completo.")
            return 0
        print("incompleto: se reanuda desde cero.")
    for intento in range(1, 4):
        try:
            print(f"intento {intento}/3: descargando...")
            t0 = time.time()
            ultimo = [0]

            def _progreso(bloque, tam_bloque, tam_total):
                nonlocal_t = time.time() - t0
                leido = bloque * tam_bloque
                if time.time() - ultimo[0] > 5:
                    ultimo[0] = time.time()
                    if tam_total > 0:
                        pct = 100.0 * leido / tam_total
                        print(f"  {leido/1e6:.0f}/{tam_total/1e6:.0f} MB ({pct:.1f}%) "
                              f"en {nonlocal_t:.0f}s")
                    else:
                        print(f"  {leido/1e6:.0f} MB en {nonlocal_t:.0f}s")

            urllib.request.urlretrieve(URL, DST, reporthook=_progreso)
            print(f"listo en {time.time()-t0:.0f}s: {os.path.getsize(DST):,} bytes")
            return 0
        except Exception as e:
            print(f"fallo intento {intento}: {e}")
            time.sleep(5)
    print("no se pudo descargar tras 3 intentos.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
