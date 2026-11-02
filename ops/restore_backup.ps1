param(
    [Parameter(Mandatory = $true)] [string]$SqlFile,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) {
    throw "Restore is destructive. Re-run with -ConfirmRestore after verifying the backup and target database."
}
if (-not (Test-Path -LiteralPath $SqlFile)) { throw "Backup file was not found: $SqlFile" }

Set-Location (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe manage.py restore_database --input $SqlFile --confirm-restore
if ($LASTEXITCODE -ne 0) { throw "Database restore failed." }
