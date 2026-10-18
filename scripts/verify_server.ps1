$url = "http://127.0.0.1:5000/api/v1/estaciones/ultima/"
try {
    $resp = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 30
    $json = $resp | ConvertTo-Json -Depth 3
    $json | Select-String -Pattern "estaciones|ok|timestamp"
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
}
