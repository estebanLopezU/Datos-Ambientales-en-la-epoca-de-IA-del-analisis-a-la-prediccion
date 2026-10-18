# -*- coding: utf-8 -*-
"""Zip de los datos crudos (Est_Datos + Excel_Organizado) para el Release.

Los CSV (142+166 MB) y xlsx (91+106 MB) superan el limite de 100 MB por
archivo de git, pero como ASSET de un Release se admiten hasta 2 GB.
Nivel 1: los CSV comprimen mucho; los xlsx ya vienen comprimidos.
"""
import os
import sys
import time
import zipfile

SRC = ["Est_Datos", "Excel_Organizado"]
DST = "tmp\\datos_crudos_2002_2026.zip"
NIVEL = 1


def main():
    t0 = time.time()
    if os.path.exists(DST):
        os.remove(DST)
    n = 0
    with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=NIVEL) as z:
        for carpeta in SRC:
            for raiz, _dirs, archivos in os.walk(carpeta):
                for nombre in archivos:
                    ruta = os.path.join(raiz, nombre)
                    z.write(ruta, ruta)   # conserva carpeta/ subida
                    n += 1
                    print("  +", ruta, flush=True)
    print("zip listo: %.1f MB con %d archivos en %.0f s"
          % (os.path.getsize(DST) / 1e6, n, time.time() - t0), flush=True)
    with zipfile.ZipFile(DST) as z:
        assert z.testzip() is None, "zip corrupto"
    print("verificacion OK", flush=True)


if __name__ == "__main__":
    sys.exit(main())
