$html = Invoke-WebRequest -Uri 'https://est-campus-unal.vercel.app/ambient/?consola=LUNA' -Method Get -TimeoutSec 60 -UseBasicParsing
$html.Content | Select-String -Pattern "Recargar estado|btn-recargar|document.getElementById\('recargar'\)" | Select-Object -First 10
