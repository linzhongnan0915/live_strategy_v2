param(
    [int]$Port = 8600,
    [switch]$StartPolling,
    [switch]$NoOpen,
    [int]$PollingIntervalSeconds = 15,
    [string]$NewsApiUrl = "",
    [string]$FriendApiBaseUrl = "https://news.tcx086.com",
    [ValidateSet("openbb", "none")]
    [string]$MarketDataMode = "openbb"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$argsToForward = @(
    "-Port", "$Port",
    "-PollingIntervalSeconds", "$PollingIntervalSeconds",
    "-FriendApiBaseUrl", "$FriendApiBaseUrl",
    "-MarketDataMode", "$MarketDataMode"
)

if ($StartPolling) {
    $argsToForward += "-StartPolling"
}
if ($NoOpen) {
    $argsToForward += "-NoOpen"
}
if ($NewsApiUrl -ne "") {
    $argsToForward += @("-NewsApiUrl", "$NewsApiUrl")
}

Write-Host "run_live_workstation.ps1 now launches the non-Streamlit web dashboard."
Write-Host "Forwarding to scripts\run_web_workstation.ps1"

& (Join-Path $Root "scripts\run_web_workstation.ps1") @argsToForward
