param(
    [int[]]$Ports = @(8501, 8502, 8503, 8504, 8505, 8506, 8507, 8508, 8509, 8510, 8600, 8601, 8602, 8603, 8604, 8605, 8606),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RootPattern = ($Root -replace "\\", "\\")

function Stop-MatchedProcess {
    param(
        [int]$ProcessId,
        [string]$Reason
    )
    if ($ProcessId -eq $PID) {
        return
    }
    if ($DryRun) {
        Write-Host "Would stop PID $ProcessId - $Reason"
        return
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped PID $ProcessId - $Reason"
}

$matched = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like "python*.exe" -and
    (
        ($_.CommandLine -match $RootPattern) -or
        ($_.CommandLine -like "*streamlit*dashboard/app.py*") -or
        ($_.CommandLine -like "*http.server*") -or
        ($_.CommandLine -like "*scripts/run_hosted_web_app.py*") -or
        ($_.CommandLine -like "*scripts\\run_hosted_web_app.py*") -or
        ($_.CommandLine -like "*scripts/run_live_polling.py*") -or
        ($_.CommandLine -like "*scripts\\run_live_polling.py*")
    ) -and
    (
        $_.CommandLine -like "*streamlit*dashboard/app.py*" -or
        $_.CommandLine -like "*http.server*" -or
        $_.CommandLine -like "*scripts/run_hosted_web_app.py*" -or
        $_.CommandLine -like "*scripts\\run_hosted_web_app.py*" -or
        $_.CommandLine -like "*scripts/run_live_polling.py*" -or
        $_.CommandLine -like "*scripts\\run_live_polling.py*"
    )
}

foreach ($process in $matched) {
    Stop-MatchedProcess -ProcessId $process.ProcessId -Reason "live_strategy workstation process"
}

foreach ($port in $Ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq "Listen" }
    foreach ($connection in $connections) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process -and $process.Name -like "python*.exe" -and $process.CommandLine -match $RootPattern) {
            Stop-MatchedProcess -ProcessId $process.ProcessId -Reason "listener on port $port"
        }
    }
}

Write-Host "Live workstation stop check complete."
