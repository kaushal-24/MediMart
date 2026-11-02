$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& .\.venv\Scripts\python.exe manage.py monitor_health
if ($LASTEXITCODE -ne 0) { throw "MediMart health monitor detected a failure." }
