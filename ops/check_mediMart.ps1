$ErrorActionPreference = "Stop"
$baseUrl = if ($env:MEDIMART_HEALTH_URL) { $env:MEDIMART_HEALTH_URL.TrimEnd("/") } else { "http://127.0.0.1:8000" }
$alertWebhook = if ($env:MEDIMART_ALERT_WEBHOOK) { $env:MEDIMART_ALERT_WEBHOOK.Trim() } else { "" }
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/health/live/" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) { throw "Liveness returned HTTP $($response.StatusCode)." }
    $response = Invoke-WebRequest -Uri "$baseUrl/health/ready/" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -ne 200) { throw "Readiness returned HTTP $($response.StatusCode)." }
    Write-Host "MediMart is healthy: $baseUrl"
} catch {
    $message = "MediMart health check failed at $(Get-Date -Format o): $($_.Exception.Message)"
    Add-Content -Path (Join-Path $PSScriptRoot "monitoring.log") -Value $message
    if ($alertWebhook) {
        try { Invoke-RestMethod -Uri $alertWebhook -Method Post -ContentType "application/json" -Body (@{text=$message; service="MediMart"} | ConvertTo-Json) | Out-Null } catch { Add-Content -Path (Join-Path $PSScriptRoot "monitoring.log") -Value "Alert webhook failed: $($_.Exception.Message)" }
    }
    throw $message
}
