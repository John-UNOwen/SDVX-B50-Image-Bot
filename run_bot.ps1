# Single-instance launcher for the SDVX B50 bot.
#
# Uses a named OS mutex, which is atomic even when start.bat is launched twice
# at the exact same instant, and which is automatically released if we crash
# (no stale-lock problem). Duplicate logins with the same token cause
# "The application did not respond" and make the bot flap offline.

$ErrorActionPreference = 'Stop'
$python  = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$botPath = Join-Path $PSScriptRoot 'bot.py'

function Get-BotProcesses {
    # Stop only bots that belong to THIS repo, so we never kill an unrelated
    # project's bot.py. Matches either the repo path on the command line
    # (launcher starts bot.py with an absolute path) or the venv python inside
    # the repo (anything started via this venv).
    $root = [regex]::Escape($PSScriptRoot)
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $_.CommandLine -match 'bot\.py' -and (
                $_.CommandLine -match $root -or $_.ExecutablePath -match $root
            )
        }
}

# --- Exclusive run: exactly one launcher can own the mutex -------------------
$mutex = New-Object System.Threading.Mutex($false, 'sdvx-b50-image-bot')
$owned = $false
try {
    $owned = $mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    # The previous launcher died while still holding the mutex; we now own it.
    $owned = $true
}
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
    & $python $botPath
} finally {
    try {
        $mutex.ReleaseMutex()
    } catch {
        # mutex may already be gone if the process was killed mid-run
    }
}
