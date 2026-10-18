# Ver procesos Python
Get-Process -Name python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName

# Detener cualquier proceso en el puerto 5000
$proc = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue |
         Where-Object { $_.OwningProcess }
if ($proc) {
    Write-Host "Deteniendo proceso $proc"
    Stop-Process -Id $proc.OwningProcess -Force
    Start-Sleep -Seconds 2
}

# Arrancar el servidor
Write-Host "Arrancando servidor..."
& .\scripts\05_arrancar_servidor.ps1
