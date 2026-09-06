# Stops any already-running bot.py process.
# Called by start.bat before launching, so a second instance can never connect
# with the same token (duplicate logins cause "The application did not respond").
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'bot\.py' } |
    ForEach-Object {
        Write-Host "[start] stopping old bot pid $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
