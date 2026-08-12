$port = 6907
$script = Join-Path $PSScriptRoot "start_new_server.py"

# Kill existing server on the port
$proc = netstat -ano | findstr ":$port "
if ($proc) {
    $pid = ($proc | Select-String "LISTENING" | ForEach-Object { $_ -split '\s+' | Select-Object -Last 1 })
    if ($pid) { taskkill /F /PID $pid }
    Start-Sleep -Seconds 1
}

# Start new server (truly detached, survives shell exit)
$python = (Get-Command python).Source
wmic process call create "$python $script" | Out-Null
