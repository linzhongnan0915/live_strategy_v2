param(
    [int]$IntervalSeconds = 30,
    [switch]$Once,
    [string]$NewsApiUrl = "",
    [string]$FriendApiBaseUrl = "https://news.tcx086.com",
    [ValidateSet("openbb", "none")]
    [string]$MarketDataMode = "openbb"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$PythonExe = Join-Path $Root ".venv_openbb\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$args = @(
    "scripts/run_live_polling.py",
    "--interval-seconds", "$IntervalSeconds",
    "--market-data-mode", "$MarketDataMode",
    "--friend-api-base-url", "$FriendApiBaseUrl"
)
if ($Once) {
    $args += "--once"
}
if ($NewsApiUrl -ne "") {
    $args += @("--news-api-url", "$NewsApiUrl")
}

Write-Host "Starting live polling with $PythonExe"
Write-Host "Interval: $IntervalSeconds seconds"
& $PythonExe @args
