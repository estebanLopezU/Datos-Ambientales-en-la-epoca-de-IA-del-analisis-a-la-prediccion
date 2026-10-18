$venvPy = "C:\Users\esteb\entornos_venv\est_campus\Scripts\python.exe"
$proyecto = "C:\Users\esteb\OneDrive\Desktop\Est Campus Unal"
Set-Location $proyecto

Write-Host "Arrancando servidor en segundo plano..." -ForegroundColor Green
$proc = Start-Process -FilePath $venvPy -ArgumentList "manage.py runserver 0.0.0.0:5000" `
    -RedirectStandardOutput "logs\servidor.log" `
    -RedirectStandardError "logs\servidor.err.log" `
    -NoNewWindow -PassThru

Write-Host "PID: $($proc.Id)" -ForegroundColor Yellow
