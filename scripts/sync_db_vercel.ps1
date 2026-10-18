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