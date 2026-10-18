# Est Campus Unal - estaciones meteorologicas

Dashboard y API para las estaciones automaticas **La Nubia (24)** y
**Palogrande-Postgrados (29)**, Universidad Nacional de Colombia, sede Manizales.

Lo que hace:

- **Endpoint de recepcion** (`POST /api/v1/estaciones/datos/`): recibe lecturas
  JSON de las estaciones, las valida (rangos fisicos, valores centinela) y las
  guarda en una base de datos local (SQLite). Idempotente por
  `(estacion, timestamp)`: reenviar no duplica.
- **Dashboard web** (`/`): tarjetas de valor actual, brujula de viento, grafica
  de la ventana de 24 h, mapa de ubicacion de las estaciones, pronostico y
  visibilidad (Open-Meteo) e **historial estadistico** por ano/mes/dia/hora
  con exportacion CSV y datos crudos por dia.
- **API de consulta**: ultima lectura y serie agregada para las graficas.

## Requisitos

- Python 3.12 y el entorno virtual `C:\Users\esteb\entornos_venv\est_campus`
  (vive fuera de OneDrive a proposito).
- Windows PowerShell.

## Puesta en marcha

```powershell
. .\scripts\10_activar_entorno.ps1
python manage.py migrate
python manage.py runserver 0.0.0.0:5000
```

> Puerto unico `5000` en `0.0.0.0` (la consola Ambient solo reporta ahi).
> No usar `8000` ni `127.0.0.1`: dejan zombies y la consola no llega.
> Arranque rapido: `.\scripts\05_arrancar_servidor.ps1` (mata zombies y arranca).

Abrir http://127.0.0.1:5000/ en el navegador. La base ya viene con todo el
historico cargado; si se quiere recargar (o cargar solo un tramo):

```powershell
python manage.py cargar_historicos                 # todo (minutos)
python manage.py cargar_historicos --desde 2026-09-01   # tramo reciente
```

El comando es idempotente: se puede repetir sin duplicar.

### Estado actual de la base local

`db.sqlite3` contiene el **historial completo** de ambas estaciones
(4.800.409 lecturas, ~1,1 GB): La Nubia desde **2004-01-01** y Palogrande
desde **2002-01-01**, ambas hasta **2026-10-07**. El comando es idempotente:
se puede repetir sin duplicar (la restriccion unica estacion+timestamp y
`ignore_conflicts` deciden que insertar).

## Pruebas y verificaciones

```powershell
python manage.py test estaciones            # 20 pruebas del endpoint
python scripts\16_revisar_frontend.py       # sintaxis JS + estaticos + plantilla
python scripts\17_probar_servidor.py        # servidor en vivo de punta a punta
```

## Endpoint de recepcion

`POST /api/v1/estaciones/datos/` con un objeto o una lista:

```json
{
  "estacion": 24,
  "timestamp": "2026-10-07 22:30:00",
  "temperatura": 18.4,
  "humedad_relativa": 88,
  "precipitacion": 0.0,
  "presion_barometrica": 600.5,
  "velocidad_viento": 1.2,
  "direccion_viento": 110,
  "radiacion_solar": 0.0,
  "evapotranspiracion": 0.0
}
```

`GET` al mismo URL devuelve la documentacion. Respuestas: `201` creado,
`207` procesado con advertencias (valores fuera de rango descartados),
`400` peticion invalida, `401` sin token (solo si `INGEST_TOKEN` esta definido).

Con token (opcional, para el demo en red local):

```powershell
$env:INGEST_TOKEN = "clave-secreta"
```

y la estacion envia la cabecera `Authorization: Bearer clave-secreta`.

API de consulta:

- `GET /api/v1/estaciones/ultima/` - ultima lectura de cada estacion.
- `GET /api/v1/estaciones/serie/?estacion=24` - serie de 24 h hasta ahora.
- `GET /api/v1/estaciones/serie/?estacion=24&modo=reciente` - 24 h anteriores
  a la ultima lectura guardada (para historicos sin datos en vivo).
- `GET /api/v1/estaciones/pronostico/?estacion=24` - pronostico y visibilidad
  del modelo Open-Meteo para las coordenadas de la estacion (cache 10 min).
- `GET /api/v1/estaciones/historial/?estacion=24` - estadisticas por ano;
  `&anio=2026` por mes, `&anio=2026&mes=9` por dia,
  `&anio=2026&mes=9&dia=15` por hora y `&crudos=1` las lecturas de 5 min
  de ese dia (drill-down en cascada; el panel lo explora con selectores).

## Estructura

```text
est_campus/            configuracion Django (hora America/Bogota, SQLite local)
estaciones/
  models.py            Estacion + Lectura (restriccion unica estacion+timestamp)
  api/endpoints.py     endpoint POST con validacion de rangos y centinelas
  views.py             dashboard + API de consulta (serie agregada en Python)
  pronostico.py        cliente Open-Meteo: pronostico y visibilidad (cache 10 min)
  management/commands/cargar_historicos.py   carga los CSV de Est_Datos
  templates/dashboard.html
  static/css/dashboard.css  static/js/dashboard.js (canvas puro + Leaflet)
Est_Datos/             CSV originales (cada 5 min)
Excel_Organizado/      libros por anio + README de calidad de datos
scripts/               utilidades numeradas (explorar, validar, probar)
```

## Panel Ambient (estacion 99, aislada)

Consola estilo Ambient Weather en `GET /ambient/` (no mezcla con 24/29):

- Receptor Wunderground: `GET /weatherstation/updateweatherstation.php`
  (responde `success`, idempotente por estacion+timestamp).
- APIs propias: `GET /api/v1/ambient/ultima/` y `GET /api/v1/ambient/serie/`.
- Traduce imperial a metrico y guarda extras de la consola
  (racha, UV, indoor, lluvias dia/semana/mes/anio, presion abs/rel).

Configurar la consola (Custom Server):

- IP `192.168.137.1`, puerto `5000`,
  path `/weatherstation/updateweatherstation.php`, protocolo Wunderground.
- En `est_campus/settings.py` esa IP ya esta en `ALLOWED_HOSTS`;
  para otra red usar `$env:ALLOWED_HOSTS = "192.168.1.20"`.

Probar el receptor:

```powershell
Invoke-WebRequest "http://127.0.0.1:5000/weatherstation/updateweatherstation.php?ID=x&PASSWORD=x&dateutc=2026-10-14%2019:30:00&tempf=77&humidity=50&action=updateraw"
```

Pruebas del modulo: `python manage.py test estaciones.tests_ambient` (9 pruebas).

## Notas importantes

- Las estaciones emiten cada **5 minutos** (medido en los datos reales).
  El demo a **16 segundos** es un escenario acelerado: la base local lo aguanta
  (ver `scripts/12_prueba_carga_bd.py`), solo cambia el volumen.
- SQLite basta: con las **4,8 M** de lecturas la base ocupa ~1,1 GB y las
  consultas del dashboard tardan milisegundos. El historial agrega con
  `strftime` nativo (los `Trunc*` de Django en SQLite son una funcion
  Python por fila: 15 s por consulta; con `strftime` baja a ~3 s y las
  respuestas se cachean 10 min, segunda visita instantanea).
- Ojo con los totales de lluvia de 2005 en La Nubia: el CSV original trae
  valores altos dentro del rango valido (0-200 mm por lectura) que suman
  ~104.000 mm en el anio. Es un problema del dato fuente, no de la carga.
- Las coordenadas del mapa son **aproximadas**: verificar contra la ficha
  tecnica antes de publicarlas.
- Las estaciones **no miden** visibilidad ni emiten pronostico: esas tarjetas
  se llenan con el modelo **Open-Meteo** (`/api/v1/estaciones/pronostico/`) y
  se etiquetan como "(Open-Meteo)". El indice UV tampoco se mide: se estima
  de la radiacion solar y se etiqueta como estimado.
- Unidades inferidas de la nomenclatura de la red (ver `Excel_Organizado/README.md`):
  confirmar con la ficha tecnica.

## Panel publico en Vercel (LUNA / estacion 99)

El dashboard publico vive en `https://est-campus-unal.vercel.app/ambient/?consola=LUNA`
y muestra los datos de la consola **LUNA** (estacion 99, Ambient experimentoUN).

### Requisitos para que LUNA aparezca EN LINEA

El badge **EN LINEA / OFFLINE** no indica si LUNA esta fisicamente conectada a la red,
sino si el servidor recibio una lectura **en los ultimos 10 minutos**
(`UMBRAL_OFFLINE_MIN = 10`).

Para que el panel publico muestre **EN LINEA**, tres cosas deben cumplirse a la vez:

1. **Servidor local encendido** en `0.0.0.0:5000`
   - Puerto unico para la consola Ambient (el receptor escucha ahi).
   - Arranque: `.\\scripts\\05_arrancar_servidor.ps1`

2. **LUNA enviando datos** al servidor local
   - Configurar la consola en Custom Server:
     - IP `192.168.137.1`, puerto `5000`,
     - path `/weatherstation/updateweatherstation.php`, protocolo Wunderground.
   - LUNA debe reportar periodicamente (cada 5-15 min recomendado).
   - Si LUNA entra en modo ahorro (low-power / quick-sleep), deja de reportar y el badge pasa a OFFLINE.

3. **Deploy actualizado en Vercel**
   - El panel publico sirve los datos de `db_vercel.sqlite3`, no de la DB local en tiempo real.
   - Para reflejar datos recientes hay que regenerar la DB y desplegar.

### Regenerar DB y desplegar (manual)

```powershell
# 1) Crear db_vercel.sqlite3 con ultimos 90 dias crudos + historia horaria
python scripts/crear_db_vercel.py 90

# 2) Desplegar a Vercel (produccion)
vercel deploy --prod --yes
```

El script conserva el rango completo **2002-2026** dentro del limite de 500 MB de Vercel:
- Ultimos 90 dias: crudos (resolucion total).
- Historia anterior (2002 -> hoy-90d): una lectura por hora y estacion (~420k filas).

Resultado verificado: `db_vercel.sqlite3` ~91.6 MB, 450.568 lecturas.

### Boton de recarga manual en el panel

Desde la version actual del template `ambient_consola.html`, el panel publico incluye un
boton **🔄 Recargar estado** junto al badge. Al hacer clic:

- Pide `/api/v1/ambient/ultima/` al servidor publico.
- Recalcula si LUNA esta en línea con el `hace_seg` enviado por el servidor.
- Actualiza el badge sin recargar toda la pagina.

Esto es util para verificar el estado tras un deploy o despues de reiniciar LUNA.

## Automatizacion: mantener el panel publico actualizado sin intervention manual

Vercel es serverless y no recibe datos directamente de LUNA (LUNA reporta al servidor local).
Para que el panel publico refleje datos recientes de forma automatica, se puede programar
el **Task Scheduler de Windows** para que regenerue `db_vercel.sqlite3` y haga deploy
periodicamente.

### Script de sincronizacion: `scripts/sync_db_vercel.ps1`

```powershell
# -*- coding: utf-8 -*-
# Sincroniza db_vercel.sqlite3 con db.sqlite3 y despliega a Vercel
# Ejecutar periodicamente desde Task Scheduler de Windows

$ErrorActionPreference = "Stop"
$proyecto = Split-Path -Parent $PSScriptRoot
Set-Location $proyecto

Write-Host "=== Sincronizando DB para Vercel ===" -ForegroundColor Cyan
Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

# 1) Regenerar db_vercel.sqlite3 (ultimos 90 dias crudos + historia horaria)
Write-Host "Regenerando db_vercel.sqlite3..." -ForegroundColor Yellow
python scripts/crear_db_vercel.py 90
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR al regenerar la DB" -ForegroundColor Red
    exit 1
}
Write-Host "DB regenerada OK" -ForegroundColor Green

# 2) Desplegar a Vercel
Write-Host "Desplegando a Vercel..." -ForegroundColor Yellow
vercel deploy --prod --yes
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR al desplegar a Vercel" -ForegroundColor Red
    exit 1
}
Write-Host "Deploy OK" -ForegroundColor Green

Write-Host "=== Sincronización completada ===" -ForegroundColor Cyan
```

### Configurar Task Scheduler de Windows

1. Abrir **Programador de tareas** (`taskschd.msc`).
2. **Crear tarea basica**:
   - Nombre: `Sync DB Vercel - Est Campus`
   - Desactivador: Diario.
   - Accion: Iniciar un programa.
   - Programa: `powershell.exe`
   - Argumentos: `-ExecutionPolicy Bypass -File "C:\Users\esteb\OneDrive\Desktop\Est Campus Unal\scripts\sync_db_vercel.ps1"`
3. En **Propiedades de la tarea**:
   - Pestaña **Desactivadores** -> Editar -> **Repetir tarea cada**: 30 minutos, durante: Indefinidamente.
   - Pestaña **Condiciones** -> Desmarcar "Iniciar la tarea solo si el equipo esta conectado a la corriente" (para portatil).
   - Pestaña **Configuración** -> "Si la tarea falla, reiniciar cada: 1 minuto, Intentar: 3 veces".

### Flujo automatizado

| Cada 30 min | Qué ocurre |
|---|---|
| Servidor local | Recibe datos de LUNA en `db.sqlite3` |
| Task Scheduler | Ejecuta `sync_db_vercel.ps1` |
| Script | Regenera `db_vercel.sqlite3` con datos actualizados |
| Script | Hace `vercel deploy --prod --yes` |
| Panel publico | Muestra LUNA **EN LINEA** con los datos más recientes |

> Nota: el servidor local y LUNA deben estar activos para que haya datos que sincronizar.
> Si cualquiera falla, el panel publico mostra OFFLINE hasta que se restablezca.

---

## Endpoints del panel Ambient (Vercel)

| Endpoint | Descripcion |
|---|---|
| `GET /ambient/?consola=LUNA` | Panel detalle de LUNA (badge, graficas, valores actuales). |
| `GET /api/v1/ambient/consolas/` | Lista de consolas con `en_linea`, `hace_seg`, `ultimo_reporte`. |
| `GET /api/v1/ambient/ultima/` | Ultima lectura de LUNA con `timestamp`, `hace_seg`, `umbral_offline_min`. |
| `GET /api/v1/ambient/serie/` | Serie temporal de LUNA para graficas. |
| `GET /api/v1/ambient/pronostico/` | Pronostico Open-Meteo para Manizales. |

### Respuesta ejemplo de `/api/v1/ambient/consolas/`

```json
{
  "ok": true,
  "umbral_offline_min": 10,
  "n": 1,
  "consolas": [{
    "device_id": "LUNA",
    "nombre": "LUNA",
    "en_linea": true,
    "hace_seg": 174,
    "ultimo_reporte": "2026-10-16T19:46:38.119892+00:00",
    "ip_origen": "192.168.137.245",
    "software": "AMBWeatherPro_V5.1.5",
    "temperatura": 21.5,
    "humedad_relativa": 74.0,
    "velocidad_viento": 1.5,
    "timestamp": "2026-10-16T14:46:38.117887-05:00"
  }]
}
```

`en_linea = true` si `hace_seg <= umbral_offline_min * 60` (600 s = 10 min).

## Archivos clave

| Archivo | Funcion |
|---|---|
| `estaciones/api/ambient_vistas.py` | APIs del panel Ambient (incluye `hace_seg` y `umbral_offline_min`). |
| `estaciones/templates/ambient_consola.html` | Panel detalle de LUNA con boton de recarga y badge `#estado`. |
| `scripts/crear_db_vercel.py` | Genera la DB ligera para Vercel (rango 2002-2026, <500 MB). |
| `scripts/sync_db_vercel.ps1` | Sincroniza DB y despliega a Vercel (para Task Scheduler). |
| `scripts/05_arrancar_servidor.ps1` | Arranca el servidor local en puerto 5000. |

