param(
    [int]$Port = 8600,
    [switch]$StartPolling,
    [int]$PollingIntervalSeconds = 15,
    [string]$NewsApiUrl = "",
    [string]$FriendApiBaseUrl = "https://news.tcx086.com",
    [ValidateSet("openbb", "none")]
    [string]$MarketDataMode = "openbb",
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-PortInUse {
    param([int]$CandidatePort)
    $connection = Get-NetTCPConnection -LocalPort $CandidatePort -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Find-AvailablePort {
    param([int]$StartPort)
    for ($candidate = $StartPort; $candidate -le ($StartPort + 50); $candidate++) {
        if (-not (Test-PortInUse -CandidatePort $candidate)) {
            return $candidate
        }
        Write-Host "Port $candidate already in use; trying $($candidate + 1)"
    }
    throw "No available web dashboard port found from $StartPort to $($StartPort + 50)."
}

$Port = Find-AvailablePort -StartPort $Port
$OutputDir = Join-Path $Root "output"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$ServerLog = Join-Path $OutputDir "web_dashboard_server.log"
$ServerErr = Join-Path $OutputDir "web_dashboard_server.err.log"
$PollingLog = Join-Path $OutputDir "web_live_polling.log"
$PollingErr = Join-Path $OutputDir "web_live_polling.err.log"

$PollingProcess = $null
if ($StartPolling) {
    $PollingPython = Join-Path $Root ".venv_openbb\Scripts\python.exe"
    if (-not (Test-Path $PollingPython)) {
        $PollingPython = "python"
    }
    $pollArgs = @(
        "scripts/run_live_polling.py",
        "--interval-seconds", "$PollingIntervalSeconds",
        "--market-data-mode", "$MarketDataMode",
        "--friend-api-base-url", "$FriendApiBaseUrl"
    )
    if ($NewsApiUrl -ne "") {
        $pollArgs += @("--news-api-url", "$NewsApiUrl")
    }
    $PollingProcess = Start-Process -FilePath $PollingPython -ArgumentList $pollArgs -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $PollingLog -RedirectStandardError $PollingErr -PassThru
    Write-Host "Started live polling process: $($PollingProcess.Id)"
}

$ServerProcess = Start-Process -FilePath "python" -ArgumentList @("-m", "http.server", "$Port", "--bind", "127.0.0.1") -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $ServerLog -RedirectStandardError $ServerErr -PassThru
Write-Host "Started web dashboard server: $($ServerProcess.Id)"

$base = "http://localhost:$Port/web_dashboard"
$ready = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "$base/market.html" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        if ($ServerProcess.HasExited) {
            Write-Host "Web dashboard server exited before becoming ready. Exit code: $($ServerProcess.ExitCode)"
            if (Test-Path $ServerErr) { Get-Content $ServerErr -Tail 40 }
            exit 1
        }
    }
}

if (-not $ready) {
    Write-Host "Web dashboard did not become ready at $base"
    if (Test-Path $ServerErr) { Get-Content $ServerErr -Tail 40 }
    exit 1
}

$urls = @(
    "$base/market.html",
    "$base/risk.html",
    "$base/strategies.html"
)

if (-not $NoOpen) {
    foreach ($url in $urls) {
        Start-Process $url
    }
}

Write-Host "Web risk workstation started:"
Write-Host "Market Monitor: $($urls[0])"
Write-Host "Risk Factors:   $($urls[1])"
Write-Host "Strategies:     $($urls[2])"
Write-Host "Data refresh:   cells update via browser fetch; no full page reload."
if ($StartPolling) {
    Write-Host "Live polling:   started, interval $PollingIntervalSeconds seconds, mode $MarketDataMode"
}
