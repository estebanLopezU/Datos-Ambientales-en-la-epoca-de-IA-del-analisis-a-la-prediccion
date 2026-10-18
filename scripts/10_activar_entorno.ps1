# Activa el entorno virtual de Django para el proyecto Est Campus UNAL.
#
# Uso:  .\scripts\10_activar_entorno.ps1
# (Si PowerShell bloquea la ejecucion, ver la nota al final del archivo.)

$ErrorActionPreference = "Stop"

$venv = "C:\Users\esteb\entornos_venv\est_campus"
$activate = Join-Path $venv "Scripts\Activate.ps1"

if (-not (Test-Path $activate)) {
    Write-Host "No se encontro el entorno virtual en: $venv" -ForegroundColor Red
    Write-Host "Crearlo con:  python -m venv $venv" -ForegroundColor Yellow
    exit 1
}

& $activate

Write-Host ""
Write-Host "Entorno activo. Django:" -ForegroundColor Green
python -c "import django; print('  Django', django.get_version())"
Write-Host ""
Write-Host "Para arrancar (PUERTO UNICO 5000):  python manage.py runserver 0.0.0.0:5000" -ForegroundColor Cyan
Write-Host "Para desactivar:  deactivate" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTA: este script activa el entorno en la sesion actual de PowerShell." -ForegroundColor DarkGray
Write-Host "Debes usar 'punto-espacio' para que el entorno persista en tu terminal:" -ForegroundColor DarkGray
Write-Host "    . .\scripts\10_activar_entorno.ps1" -ForegroundColor White

# Si aparece "la ejecucion de scripts esta deshabilitada en este sistema",
# ejecuta UNA vez en PowerShell como administrador:
#     Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
