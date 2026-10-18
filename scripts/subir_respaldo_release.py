# -*- coding: utf-8 -*-
"""Crea el release respaldo-db-2002-2026 y sube tmp/db_historico_2002_2026.zip.

Usa el token del Credential Manager de Windows (git credential fill), el
mismo que permite hacer push, que trae scope repo.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ZIP = "tmp\\db_historico_2002_2026.zip"
TAG = "respaldo-db-2002-2026"
REPO = "estebanLopezU/mineria_de_datos_proyecto"

BODY = """Respaldo completo de db.sqlite3 con el historial de las estaciones UNAL Manizales.

- Lecturas: 4.800.936 (La Nubia 24: 2.256.189 | Palogrande 29: 2.544.220 | Ambient 99: 527)
- Rango: 2002-01-01 05:00:00 .. 2026-10-16 20:05:59 (America/Bogota)
- sha256 db.sqlite3: be21582b9fb0bf6917eac824e054de0b58c5be1bfd5ff4280ce7ff0a7d0fa3cc

**Restaurar:**
```powershell
# 1. Descargar db_historico_2002_2026.zip a la raiz del proyecto
# 2. Verificar el sha256 contra el manifiesto (opcional)
Expand-Archive db_historico_2002_2026.zip -DestinationPath .
python manage.py runserver 0.0.0.0:5000
```
"""


def token():
    out = subprocess.run(["git", "credential", "fill"],
                         input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    sys.exit("sin token en credential manager")


def api(url, data=None, method=None, headers=None, raw=None):
    h = {"Authorization": "token " + TOKEN,
         "User-Agent": "est-campus-backup",
         "Accept": "application/vnd.github+json"}
    if headers:
        h.update(headers)
    body = None
    if raw is not None:
        body = raw
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h,
                                 method=method or ("POST" if body else "GET"))
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    global TOKEN
    TOKEN = token()
    if not os.path.exists(ZIP):
        sys.exit("falta " + ZIP)
    # Release existente: reutilizar o recrear.
    rels = api("https://api.github.com/repos/%s/releases" % REPO)
    rel = next((r for r in rels if r["tag_name"] == TAG), None)
    if rel:
        print("release ya existe id", rel["id"])
        # Quitar assets previos para reemplazar.
        for a in rel["assets"]:
            print("borrando asset previo:", a["name"])
            api(a["url"], method="DELETE")
    else:
        rel = api("https://api.github.com/repos/%s/releases" % REPO, data={
            "tag_name": TAG,
            "name": "Respaldo base de datos historico 2002-2026",
            "body": BODY,
            "draft": False,
            "prerelease": False,
        })
        print("release creado id", rel["id"], rel["html_url"])
    up = rel["upload_url"].split("{")[0] + "?name=" + os.path.basename(ZIP)
    print("subiendo %.1f MB..." % (os.path.getsize(ZIP) / 1e6), flush=True)
    t0 = time.time()
    with open(ZIP, "rb") as f:
        raw = f.read()
    asset = api(up, raw=raw,
                headers={"Content-Type": "application/zip"})
    print("asset id", asset["id"], "| url:", asset["browser_download_url"],
          "| %.0f s" % (time.time() - t0))
    print("tamanio reportado:", asset["size"], "bytes")


if __name__ == "__main__":
    sys.exit(main())
