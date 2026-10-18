# -*- coding: utf-8 -*-
"""Sube un zip como asset de un release de GitHub.

Usa el token del Credential Manager de Windows (git credential fill), el
mismo que permite hacer push, que trae scope repo.

Uso:
    python scripts/subir_respaldo_release.py [zip] [tag]
Por defecto: tmp/db_historico_2002_2026.zip respaldo-db-2002-2026
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = "estebanLopezU/Datos-Ambientales-en-la-epoca-de-IA-del-analisis-a-la-prediccion"
DEFAULTS = ("tmp\\db_historico_2002_2026.zip", "respaldo-db-2002-2026")


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
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    global TOKEN
    TOKEN = token()
    zip_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULTS[0]
    tag = sys.argv[2] if len(sys.argv) > 2 else DEFAULTS[1]
    if not os.path.exists(zip_path):
        sys.exit("falta " + zip_path)
    nombre = os.path.basename(zip_path)
    rels = api("https://api.github.com/repos/%s/releases" % REPO)
    rel = next((r for r in rels if r["tag_name"] == tag), None)
    if not rel:
        sys.exit("no existe el release con tag " + tag)
    previo = next((a for a in rel["assets"] if a["name"] == nombre), None)
    if previo:
        print("borrando asset previo:", nombre)
        api(previo["url"], method="DELETE")
    up = rel["upload_url"].split("{")[0] + "?name=" + nombre
    mb = os.path.getsize(zip_path) / 1e6
    print("subiendo %s (%.1f MB) a %s..." % (nombre, mb, tag), flush=True)
    t0 = time.time()
    with open(zip_path, "rb") as f:
        raw = f.read()
    asset = api(up, raw=raw, headers={"Content-Type": "application/zip"})
    print("asset id", asset["id"], "| %.0f s" % (time.time() - t0))
    print("url:", asset["browser_download_url"])
    print("tamanio reportado:", asset["size"], "bytes | state:",
          asset["state"])


if __name__ == "__main__":
    sys.exit(main())

