# -*- coding: utf-8 -*-
"""
Arranca el servidor de Django, comprueba que todo responde y lo detiene.

No deja procesos colgados: el servidor se termina en el bloque finally.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = r"C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
PY = r"C:\Users\esteb\entornos_venv\est_campus\Scripts\python.exe"
PUERTO = 8765
RAIZ = f"http://127.0.0.1:{PUERTO}"

URLS = [
    ("Dashboard", "/"),
    ("Documentacion del endpoint", "/api/v1/estaciones/datos/"),
    ("API ultima lectura", "/api/v1/estaciones/ultima/"),
    # Sin modo=reciente la ventana "hasta ahora" sale vacia con historicos;
    # por eso el dashboard usa el modo anclado a la ultima lectura.
    ("API serie 24 h (est. 24)", "/api/v1/estaciones/serie/?estacion=24&modo=reciente"),
    ("API serie 24 h (est. 29)", "/api/v1/estaciones/serie/?estacion=29&modo=reciente"),
    ("Admin", "/admin/login/"),
]

LECTURA_PRUEBA = {
    "estacion": 24,
    "timestamp": "2026-10-07 23:59:00",
    "temperatura": 17.25,
    "humedad_relativa": 91,
    "precipitacion": 0.0,
    "presion_barometrica": 599.8,
    "velocidad_viento": 0.9,
    "direccion_viento": 205,
    "radiacion_solar": 0.0,
    "evapotranspiracion": 0.0,
}


def esperar_servidor(timeout=40):
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(RAIZ + "/", timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    return False


def post(url, datos):
    """Envia un POST JSON. Devuelve (estado, cuerpo)."""
    peticion = urllib.request.Request(
        url, data=json.dumps(datos).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main():
    print("=" * 72)
    print("PRUEBA DEL SERVIDOR EN VIVO")
    print("=" * 72)

    servidor = subprocess.Popen(
        [PY, "manage.py", "runserver", f"127.0.0.1:{PUERTO}", "--noreload"],
        cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    fallos = []
    try:
        if not esperar_servidor():
            print("El servidor no arranco.")
            if servidor.stdout:
                print(servidor.stdout.read()[:3000])
            return 1
        print(f"servidor listo en {RAIZ}\n")

        print("--- peticiones GET ---")
        for nombre, url in URLS:
            try:
                with urllib.request.urlopen(RAIZ + url, timeout=25) as r:
                    cuerpo = r.read().decode("utf-8", "replace")
                    estado = r.status
                ok = estado == 200 and len(cuerpo) > 100
                print(f"  {'OK  ' if ok else 'FALLA'} {nombre:<30} "
                      f"{estado}  {len(cuerpo):>8,} bytes")
                if not ok:
                    fallos.append(nombre)
            except Exception as exc:
                print(f"  FALLA {nombre:<30} {exc}")
                fallos.append(nombre)

        print("\n--- el dashboard trae contenido real ---")
        with urllib.request.urlopen(RAIZ + "/", timeout=25) as r:
            html = r.read().decode("utf-8", "replace")
        for marca in ("La Nubia", "Palogrande", "Ubicacion de las estaciones",
                      "Ultimas 24 horas", "id=\"mapa\"", "js-valor",
                      "data-modo"):
            ok = marca in html
            print(f"  {'OK  ' if ok else 'FALLA'} contiene {marca!r}")
            if not ok:
                fallos.append(f"dashboard sin {marca}")

        print("\n--- endpoint de recepcion ---")
        url_datos = RAIZ + "/api/v1/estaciones/datos/"
        estado, cuerpo = post(url_datos, LECTURA_PRUEBA)
        ok = estado in (201, 207)
        print(f"  {'OK  ' if ok else 'FALLA'} POST guarda lectura  "
              f"{estado}  {cuerpo}")
        if not ok:
            fallos.append("POST endpoint")

        estado, cuerpo = post(url_datos, LECTURA_PRUEBA)
        ok = '"duplicadas": 1' in cuerpo
        print(f"  {'OK  ' if ok else 'FALLA'} reenviar no duplica  {cuerpo}")
        if not ok:
            fallos.append("idempotencia")

        estado, cuerpo = post(url_datos, {"estacion": 24})
        ok = estado == 400
        print(f"  {'OK  ' if ok else 'FALLA'} dato incompleto -> 400  {estado}")
        if not ok:
            fallos.append("validacion")

        print("\n--- serie para las graficas ---")
        with urllib.request.urlopen(
                RAIZ + "/api/v1/estaciones/serie/?estacion=24&modo=reciente",
                timeout=25) as r:
            datos = json.loads(r.read().decode("utf-8"))
        n = datos.get("puntos", 0)
        ok = datos.get("ok") and n > 0
        print(f"  {'OK  ' if ok else 'FALLA'} puntos en la ventana   "
              f"{n} puntos de {datos.get('lecturas_en_ventana', 0):,} lecturas")
        if not ok:
            fallos.append("serie sin puntos")

    finally:
        servidor.terminate()
        try:
            servidor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            servidor.kill()
        print("\nservidor detenido")

    print()
    if fallos:
        print("FALLOS:", ", ".join(fallos))
        return 1
    print("TODO RESPONDE CORRECTAMENTE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
