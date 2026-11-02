$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& .\.venv\Scripts\python.exe manage.py process_notification_queue --limit 200
if ($LASTEXITCODE -ne 0) { throw "Notification queue processing failed." }
