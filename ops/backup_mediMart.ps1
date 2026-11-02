$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& .\.venv\Scripts\python.exe manage.py backup_database
if ($LASTEXITCODE -ne 0) { throw "Database backup failed." }

# Keep private regulated uploads with the matching database backup.
$latest = Get-ChildItem .\backups\medimart-*.sql | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$archive = Join-Path (Resolve-Path .\backups) ("private-media-" + $latest.BaseName.Replace("medimart-", "") + ".zip")
if (Test-Path .\private_media) {
    Compress-Archive -Path .\private_media -DestinationPath $archive -Force
}
Write-Host "MediMart backup completed: $latest"
