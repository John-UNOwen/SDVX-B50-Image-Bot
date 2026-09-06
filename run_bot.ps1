# Single-instance launcher for the SDVX B50 bot.
#
# Guarded by a lock dir in %TEMP% so that launching start.bat twice at the same
# instant still results in exactly ONE bot. Duplicate logins with the same
# token cause "The application did not respond".

$ErrorActionPreference = 'Stop'
$lock = Join-Path $env:TEMP 'sdvx-b50-bot.lock'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Get-BotProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'bot\.py' }
}

# --- Acquire the exclusive lock (atomic mkdir; stale locks are cleared) ------
$acquired = $false
for ($attempt = 0; $attempt -lt 5 -and -not $acquired; $attempt++) {
    try {
        New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
        $acquired = $true
    } catch {
        if (Get-BotProcesses) {
            Write-Host '[start] Bot is already running in another window. Use that window.'
            exit 1
        }
        # Lock exists but no bot is running: either a concurrent launcher is
        # still starting (give it a moment to bring its bot up), or it's a
        # stale lock from a crash. Re-check, then clear and retry.
        Start-Sleep -Seconds 2
        if (Get-BotProcesses) {
            Write-Host '[start] Bot is already running in another window. Use that window.'
            exit 1
        }
        Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}
if (-not $acquired) {
    Write-Host '[start] Could not acquire the run lock. Try again.'
    exit 1
}

# --- Stop any leftover instance, then start exactly one ----------------------
Get-BotProcesses | ForEach-Object {
    Write-Host "[start] stopping old bot pid $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 400
Get-BotProcesses | ForEach-Object {
    Write-Host "[start] stopping straggler bot pid $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

try {
    Write-Host '[start] Starting bot (press Ctrl+C to stop)...'
    & $python bot.py
} finally {
    Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue
}
