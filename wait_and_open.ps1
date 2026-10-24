# Helper script: wait until the local service port is ready, then open the browser.
# Pure English on purpose - PowerShell scripts with non-ASCII chars may fail to parse
# unless saved as UTF-8 with BOM.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File wait_and_open.ps1 -Port 8002 -TimeoutSec 60

param(
    [int]$Port = 8002,
    [int]$TimeoutSec = 60
)

$target = "127.0.0.1"
$url = "http://${target}:$Port"
$deadline = (Get-Date).AddSeconds($TimeoutSec)

function Test-PortOpen {
    param([string]$TargetHost, [int]$TargetPort)
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async = $client.BeginConnect($TargetHost, $TargetPort, $null, $null)
        $ok = $async.AsyncWaitHandle.WaitOne(1000, $false)
        if ($ok -and $client.Connected) {
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        if ($client) { $client.Close() }
    }
}

while ((Get-Date) -lt $deadline) {
    if (Test-PortOpen -TargetHost $target -TargetPort $Port) {
        # Port is open; give the app a short moment to finish booting
        # so the first page load does not hit a half-ready server.
        Start-Sleep -Milliseconds 1200
        Start-Process $url
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

# Timed out: the service never came up. Do not open a dead URL.
exit 1
