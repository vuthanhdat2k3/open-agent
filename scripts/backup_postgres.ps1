<#
.SYNOPSIS
    Daily backup of the OpenAgent Postgres database.

.DESCRIPTION
    Runs `pg_dump` inside the running `postgres` container, compresses the
    output, and writes it to backups/ (gitignored — this directory holds
    real user/chat data and must never be committed). Keeps the most recent
    $RetainCount backups and deletes older ones.

    Safe to run while the stack is up: pg_dump takes a consistent snapshot
    without blocking reads/writes on the running database.

.PARAMETER RetainCount
    Number of most recent backups to keep. Older backups beyond this count
    are deleted. Default: 14 (roughly two weeks at one backup per day).

.EXAMPLE
    .\scripts\backup_postgres.ps1
    Runs a backup with the default 14-backup retention.

.EXAMPLE
    .\scripts\backup_postgres.ps1 -RetainCount 30
    Keeps 30 days of backups instead of the default 14.
#>

[CmdletBinding()]
param(
    [int]$RetainCount = 14
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackupDir = Join-Path $RepoRoot "backups"
$ContainerName = "open-agent-postgres-1"
$EnvFile = Join-Path $RepoRoot ".env"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

# Read DB name/user from .env without echoing the password.
if (-not (Test-Path $EnvFile)) {
    throw ".env not found at $EnvFile - cannot determine Postgres credentials."
}
$envContent = Get-Content $EnvFile -Raw
$dbUser = [regex]::Match($envContent, "(?m)^OPENAGENT_POSTGRES_USER=(.+)$").Groups[1].Value.Trim()
$dbName = [regex]::Match($envContent, "(?m)^OPENAGENT_POSTGRES_DB=(.+)$").Groups[1].Value.Trim()
if (-not $dbUser) { $dbUser = "openagent" }
if (-not $dbName) { $dbName = "openagent" }

$running = docker ps --filter "name=$ContainerName" --format "{{.Names}}"
if ($running -ne $ContainerName) {
    throw "Postgres container '$ContainerName' is not running. Start it with: docker compose up -d postgres"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpFileInContainer = "/tmp/openagent-backup-$timestamp.dump"
$localDumpPath = Join-Path $BackupDir "openagent-backup-$timestamp.dump"
$localGzPath = "$localDumpPath.gz"

Write-Host "Running pg_dump inside $ContainerName..."
docker exec $ContainerName pg_dump --username=$dbUser --dbname=$dbName --format=custom --file=$dumpFileInContainer
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE"
}

Write-Host "Copying dump out of the container..."
docker cp "${ContainerName}:${dumpFileInContainer}" $localDumpPath
docker exec $ContainerName rm -f $dumpFileInContainer

Write-Host "Compressing..."
# .NET GzipStream avoids depending on an external gzip binary being on PATH.
$inputStream = [System.IO.File]::OpenRead($localDumpPath)
$outputStream = [System.IO.File]::Create($localGzPath)
$gzipStream = New-Object System.IO.Compression.GzipStream($outputStream, [System.IO.Compression.CompressionMode]::Compress)
try {
    $inputStream.CopyTo($gzipStream)
} finally {
    $gzipStream.Dispose()
    $outputStream.Dispose()
    $inputStream.Dispose()
}
Remove-Item $localDumpPath -Force

$sizeKb = [math]::Round((Get-Item $localGzPath).Length / 1KB, 1)
Write-Host "Backup written: $localGzPath ($sizeKb KB)"

# Retention: keep only the $RetainCount most recent backups.
$allBackups = Get-ChildItem -Path $BackupDir -Filter "openagent-backup-*.dump.gz" | Sort-Object Name -Descending
if ($allBackups.Count -gt $RetainCount) {
    $toDelete = $allBackups | Select-Object -Skip $RetainCount
    foreach ($old in $toDelete) {
        Write-Host "Removing old backup: $($old.Name)"
        Remove-Item $old.FullName -Force
    }
}

$retainedCount = if ($allBackups.Count -gt $RetainCount) { $RetainCount } else { $allBackups.Count }
Write-Host "Backup complete. $retainedCount backup(s) retained in $BackupDir."
