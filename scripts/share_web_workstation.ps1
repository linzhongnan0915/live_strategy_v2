param(
    [int]$Port = 8600,
    [switch]$StartPolling,
    [int]$PollingIntervalSeconds = 15,
    [string]$NewsApiUrl = "https://news.tcx086.com/analysis/patterns",
    [ValidateSet("openbb", "none")]
    [string]$MarketDataMode = "openbb"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Cloudflared = Join-Path $Root "tools\cloudflared.exe"
if (-not (Test-Path $Cloudflared)) {
    throw "tools\cloudflared.exe not found. Download cloudflared before sharing."
}

$OutputDir = Join-Path $Root "output"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$TunnelLog = Join-Path $OutputDir "cloudflare_tunnel.log"
$TunnelErr = Join-Path $OutputDir "cloudflare_tunnel.err.log"

.\scripts\stop_live_workstation.ps1 | Out-Host

$workstationArgs = @(
    "-Port", "$Port",
    "-NoOpen"
)
if ($StartPolling) {
    $workstationArgs += @(
        "-StartPolling",
        "-PollingIntervalSeconds", "$PollingIntervalSeconds",
        "-MarketDataMode", "$MarketDataMode",
        "-NewsApiUrl", "$NewsApiUrl"
    )
}

$workstation = Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts\run_web_workstation.ps1"
) + $workstationArgs -WorkingDirectory $Root -WindowStyle Hidden -PassThru

Write-Host "Started local web workstation process: $($workstation.Id)"
Start-Sleep -Seconds 8

$localUrl = "http://localhost:$Port/web_dashboard/index.html"
try {
    $response = Invoke-WebRequest -Uri $localUrl -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -ne 200) {
        throw "local workstation returned $($response.StatusCode)"
    }
} catch {
    throw "Local workstation is not ready at $localUrl. Error: $($_.Exception.Message)"
}

$tunnel = Start-Process -FilePath $Cloudflared -ArgumentList @(
    "tunnel",
    "--url",
    "http://localhost:$Port"
) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $TunnelLog -RedirectStandardError $TunnelErr -PassThru

Write-Host "Started Cloudflare tunnel process: $($tunnel.Id)"
Write-Host "Waiting for shareable URL..."

$shareUrl = $null
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 1
    $combined = ""
    if (Test-Path $TunnelLog) {
        $combined += Get-Content $TunnelLog -Raw
    }
    if (Test-Path $TunnelErr) {
        $combined += "`n" + (Get-Content $TunnelErr -Raw)
    }
    $match = [regex]::Match($combined, "https://[-a-zA-Z0-9.]+\.trycloudflare\.com")
    if ($match.Success) {
        $shareUrl = $match.Value
        break
    }
}

if (-not $shareUrl) {
    Write-Host "Tunnel started but URL was not found yet. Check:"
    Write-Host $TunnelLog
    Write-Host $TunnelErr
    exit 1
}

Write-Host ""
Write-Host "Share this landing page:"
Write-Host "$shareUrl/web_dashboard/index.html"
Write-Host ""
Write-Host "Direct screens:"
Write-Host "Market:     $shareUrl/web_dashboard/market.html"
Write-Host "Risk:       $shareUrl/web_dashboard/risk.html"
Write-Host "Strategies: $shareUrl/web_dashboard/strategies.html"
Write-Host ""
Write-Host "Keep this computer running. Stop everything with:"
Write-Host ".\scripts\stop_live_workstation.ps1"
