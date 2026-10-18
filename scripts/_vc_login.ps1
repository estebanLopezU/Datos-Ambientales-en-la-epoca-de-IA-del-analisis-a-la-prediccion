# Login interactivo de Vercel: imprime el link/codigo, espera al usuario,
# y luego publica automaticamente.
Write-Host "== paso 1: login ==" | Tee-Object -FilePath logs\_vc_login.log
vercel login --scope all 2>&1 | Tee-Object -FilePath logs\_vc_login.log -Append
Write-Host ("LOGIN_EXIT=" + $LASTEXITCODE) | Tee-Object -FilePath logs\_vc_login.log -Append
if ($LASTEXITCODE -eq 0) {
  Write-Host "== paso 2: whoami ==" | Tee-Object -FilePath logs\_vc_login.log -Append
  vercel whoami 2>&1 | Tee-Object -FilePath logs\_vc_login.log -Append
  Write-Host "== paso 3: deploy prod ==" | Tee-Object -FilePath logs\_vc_login.log -Append
  vercel deploy --prod --yes 2>&1 | Tee-Object -FilePath logs\_dep2.log -Append
} else {
  Write-Host "LOGIN_NO_COMPLETADO" | Tee-Object -FilePath logs\_vc_login.log -Append
}
