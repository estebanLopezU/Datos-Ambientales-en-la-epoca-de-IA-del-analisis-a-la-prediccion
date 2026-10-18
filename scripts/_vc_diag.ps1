# -*- coding: utf-8 -*-
# Diagnostico rapido de autenticacion vercel.
$err = { param($e) Write-Host "ERROR: $e" -ForegroundColor Red }
try {
  Write-Host "== env VERCEL =="
  (Get-ChildItem Env: | Where-Object { $_.Name -like '*ERCEL*' } | Format-Table Name, Value -AutoSize)
  Write-Host "== APPDATA/vercel =="; if (Test-Path $env:APPDATA\vercel) { ls $env:APPDATA\vercel } else { "no existe" }
  Write-Host "== LOCALAPPDATA/vercel =="; if (Test-Path $env:LOCALAPPDATA\vercel) { ls $env:LOCALAPPDATA\vercel } else { "no existe" }
  Write-Host "== .vercel/ =="; if (Test-Path '.\.vercel') { ls '.\.vercel' } else { "no existe" }
  Write-Host "== tokens list =="; vercel tokens list 2>&1 | Select-Object -First 8
  Write-Host "== deploy --debug =="; vercel deploy --prod --yes --debug 2>&1 | Select-Object -F 25
} catch {
  Write-Host "ERR: $_" -ForegroundColor Red
}
