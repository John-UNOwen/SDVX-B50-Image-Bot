# Single-instance launcher for the SDVX B50 bot.
#
# Uses a named OS mutex, which is atomic even when start.bat is launched twice
# at the exact same instant, and which is automatically released if we crash
# (no stale-lock problem). Duplicate logins with the same token cause
# "The application did not respond" and make the bot flap offline.

$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

function Get-BotProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'bot\.py' }
}

# --- Exclusive run: exactly one launcher can own the mutex -------------------
$mutex = New-Object System.Threading.Mutex($false, 'sdvx-b50-bot')
$owned = $mutex.WaitOne(0)
if (-not $owned) {
    Write-Host '[start] Bot is already running in another window. Use that window.'
    exit 1
}

try {
    # Defensive: stop any bot instance from an older launcher version.
    Get-BotProcesses | ForEach-Object {
        Write-Host "[start] stopping old bot pid $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host '[start] Starting bot (press Ctrl+C to stop)...'
    & $python bot.py
} finally {
    try {
        $mutex.ReleaseMutex()
    } catch {
        # mutex may already be gone if the process was killed mid-run
    }
}
