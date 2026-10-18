# Arranca el servidor UNICO en 0.0.0.0:5000 (puerto de la consola Ambient).
#
# Uso:  .\scripts\05_arrancar_servidor.ps1
# Mata zombies python en 5000/8000 antes de arrancar para no duplicar.

$ErrorActionPreference = "Stop"
$venvPy = "C:\Users\esteb\entornos_venv\est_campus\Scripts\python.exe"
$proyecto = Split-Path -Parent $PSScriptRoot
Set-Location $proyecto

foreach ($p in @(5000, 8000)) {
    $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        try {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -like "python*") {
                Write-Host "Matando zombie $($proc.ProcessName) PID $($proc.Id) en puerto $p" -ForegroundColor Yellow
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            } else {
                Write-Host "Puerto $p ocupado por $($proc.ProcessName) PID $($proc.Id): no se toca" -ForegroundColor Red
            }
        } catch {}
    }
}

Write-Host "Arrancando en 0.0.0.0:5000 ..." -ForegroundColor Green
& $venvPy manage.py runserver 0.0.0.0:5000
