# -*- coding: utf-8 -*-
"""
Endpoint de recepcion de datos de las estaciones.

Diseno:
  - POST JSON con los datos de una estacion.
  - Idempotente por (estacion, timestamp): reenviar el mismo dato no duplica.
  - Acepta un objeto o una lista de objetos (lote).
  - Valida rangos y descarta valores centinela, informandolo en la respuesta.

Codigos de respuesta:
  201  se guardo al menos una lectura
  207  se proceso el lote pero hubo elementos invalidos
  400  la peticion no es valida
  401  falta o falla el token (si INGEST_TOKEN esta configurado)

Autenticacion: si se define la variable de entorno INGEST_TOKEN, se exige la
cabecera  Authorization: Bearer <token> . Si no se define, el endpoint queda
abierto (util para el demo en red local).
"""
import json
import os
from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..models import Estacion, Lectura

# Variables que acepta el endpoint y su rango fisicamente valido.
# Los valores centinela detectados en los CSV (humedad 255, viento 113.99,
# presion 0 hPa, etc.) caen fuera de estos rangos y se rechazan.
RANGOS = {
    "temperatura": (-10.0, 50.0),
    "humedad_relativa": (0.0, 100.0),
    "precipitacion": (0.0, 200.0),
    "presion_barometrica": (400.0, 900.0),
    "velocidad_viento": (0.0, 60.0),
    "direccion_viento": (0.0, 360.0),
    "radiacion_solar": (0.0, 1500.0),
    "evapotranspiracion": (0.0, 100.0),
}

# Formatos de fecha/hora que se aceptan desde la estacion.
FORMATOS_TS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)

TOKEN = os.environ.get("INGEST_TOKEN", "").strip()


def _autorizado(request):
    """Si hay token configurado lo valida; si no, deja pasar."""
    if not TOKEN:
        return True
    cabecera = request.headers.get("Authorization", "")
    if not cabecera.startswith("Bearer "):
        return False
    return cabecera[len("Bearer "):].strip() == TOKEN


def _parse_timestamp(valor):
    """Convierte el timestamp de la estacion a datetime con zona horaria."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        # Epoch en segundos.
        try:
            return timezone.datetime.fromtimestamp(
                valor, tz=timezone.get_current_timezone())
        except (ValueError, OSError, OverflowError):
            return None

    if not isinstance(valor, str) or not valor.strip():
        return None

    texto = valor.strip().replace("Z", "").replace("/", "-")
    for fmt in FORMATOS_TS:
        try:
            ingenuo = datetime.strptime(texto, fmt)
        except ValueError:
            continue
        # Se interpreta en la zona horaria del proyecto (America/Bogota).
        return timezone.make_aware(ingenuo, timezone.get_current_timezone())
    return None


def _parse_numero(valor):
    """Convierte a float aceptando coma decimal (locale es-co). None si no es numero."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _validar_uno(dato):
    """
    Valida un registro individual.

    Devuelve (campos, errores). Si hay errores graves el registro se descarta;
    los valores individuales invalidos se descartan uno a uno y se informan como
    advertencias, de modo que una lectura sirva aunque un sensor falle.
    """
    if not isinstance(dato, dict):
        return None, ["se esperaba un objeto JSON"]

    errores = []

    # --- estacion ---
    estacion = None
    for clave in ("estacion", "estacion_id", "codigo", "id"):
        if clave in dato and dato[clave] not in (None, ""):
            try:
                estacion = Estacion.objects.get(pk=int(dato[clave]))
            except (Estacion.DoesNotExist, ValueError, TypeError):
                errores.append(f"estacion desconocida: {dato[clave]!r}")
            break
    if estacion is None:
        if not errores:
            errores.append("falta el campo 'estacion'")
        return None, errores

    # --- timestamp ---
    ts = _parse_timestamp(
        dato.get("timestamp") or dato.get("fecha_hora")
        or dato.get("tiempo") or dato.get("fecha"))
    if ts is None:
        return None, ["timestamp invalido o ausente"]

    # --- variables ---
    campos = {"estacion": estacion, "timestamp": ts}
    for var, (lo, hi) in RANGOS.items():
        if var not in dato:
            continue
        valor = _parse_numero(dato[var])
        if valor is None:
            if dato[var] not in (None, ""):
                errores.append(f"{var}: no es numero")
            continue
        if not (lo <= valor <= hi):
            errores.append(f"{var}: {valor} fuera del rango valido [{lo}, {hi}]")
            continue
        campos[var] = valor

    return campos, errores


def _guardar(campos):
    """Inserta la lectura si no existe. Devuelve 'creada' o 'duplicada'."""
    _obj, creada = Lectura.objects.get_or_create(
        estacion=campos["estacion"],
        timestamp=campos["timestamp"],
        defaults={k: v for k, v in campos.items()
                  if k not in ("estacion", "timestamp")},
    )
    return "creada" if creada else "duplicada"


@csrf_exempt                     # la estacion no maneja cookies de sesion ni CSRF
@require_http_methods(["POST", "GET"])
def recibir_datos(request):
    """
    Recibe lecturas de las estaciones.

    GET  -> documentacion del endpoint (util para probar en el navegador)
    POST -> guarda una lectura o un lote
    """
    if request.method == "GET":
        return JsonResponse({
            "endpoint": "/api/v1/estaciones/datos/",
            "metodo": "POST",
            "autenticacion": "Bearer" if TOKEN else "abierta (sin token)",
            "variables_aceptadas": sorted(RANGOS),
            "rangos_validos": {k: list(v) for k, v in RANGOS.items()},
            "ejemplo": {
                "estacion": 24,
                "timestamp": "2026-10-07 22:30:00",
                "temperatura": 18.4,
                "humedad_relativa": 88,
                "precipitacion": 0.0,
                "presion_barometrica": 600.5,
                "velocidad_viento": 1.2,
                "direccion_viento": 110,
                "radiacion_solar": 0.0,
                "evapotranspiracion": 0.0,
            },
        })

    if not _autorizado(request):
        return JsonResponse({"ok": False, "error": "no autorizado"}, status=401)

    try:
        cuerpo = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"ok": False, "error": "el cuerpo no es JSON valido"}, status=400)

    if isinstance(cuerpo, dict):
        registros = [cuerpo]
    elif isinstance(cuerpo, list):
        registros = cuerpo
    else:
        return JsonResponse(
            {"ok": False, "error": "se esperaba un objeto o una lista"}, status=400)

    if not registros:
        return JsonResponse(
            {"ok": False, "error": "llego una lista vacia"}, status=400)

    creadas = duplicadas = 0
    rechazos = []

    for i, dato in enumerate(registros):
        campos, errores = _validar_uno(dato)
        if campos is None:
            rechazos.append({"indice": i, "errores": errores})
            continue
        try:
            estado = _guardar(campos)
        except Exception as exc:                      # no silenciar fallos de BD
            return JsonResponse(
                {"ok": False, "error": f"fallo al guardar: {exc}"}, status=500)
        if estado == "creada":
            creadas += 1
        else:
            duplicadas += 1
        if errores:
            rechazos.append({"indice": i, "advertencias": errores})

    if creadas == 0 and rechazos:
        return JsonResponse({
            "ok": False,
            "creadas": 0,
            "duplicadas": duplicadas,
            "rechazados": rechazos,
        }, status=400 if duplicadas == 0 else 207)

    return JsonResponse({
        "ok": True,
        "creadas": creadas,
        "duplicadas": duplicadas,
        "rechazados": rechazos,
    }, status=201 if not rechazos else 207)

