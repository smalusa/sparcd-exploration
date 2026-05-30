$ErrorActionPreference = "Stop"

$lbIp = "149.165.159.15"
$hostName = "llm.jetstream-cloud.org"
$baseUrl = "https://$hostName/llama-4-scout/v1"

Write-Host "== Models =="
curl.exe --resolve "$hostName`:443:$lbIp" --max-time 20 -s "$baseUrl/models"

Write-Host "`n== Chat completion =="
$payloadPath = Join-Path $env:TEMP "jetstream2-inference-test.json"
'{"model":"llama-4-scout","messages":[{"role":"user","content":"Reply with only the word ok."}],"max_tokens":64,"temperature":0}' | Set-Content -LiteralPath $payloadPath -Encoding ascii
curl.exe --resolve "$hostName`:443:$lbIp" --max-time 60 -s "$baseUrl/chat/completions" -H "Content-Type: application/json" -d "@$payloadPath"
