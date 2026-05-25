param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $PSScriptRoot "start_neuroweave.ps1"
$stopScript = Join-Path $PSScriptRoot "stop_neuroweave.ps1"
$logsDir = Join-Path $repoRoot "data\logs"
$runtimeDir = Join-Path $repoRoot "data\runtime"

function Assert-Health {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 5
    if ($health.status -ne "ok" -or $health.service -ne "neuroweave-api") {
        throw "Unexpected API health payload."
    }
    if (-not $health.workers.preprocessing -or -not $health.workers.epoch -or -not $health.workers.erp) {
        throw "Expected all local workers to be alive."
    }
}

function Assert-RepoOwnedListenerStopped {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return
    }

    $normalizedRepoRoot = $repoRoot.ToLowerInvariant()
    foreach ($processId in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $commandLine = if ($processInfo -and $processInfo.CommandLine) { $processInfo.CommandLine.ToLowerInvariant() } else { "" }
        if ($commandLine.Contains($normalizedRepoRoot)) {
            throw "Repo-owned listener still running on port ${Port}: PID ${processId}"
        }
    }
}

Set-Location $repoRoot

Write-Host "Starting NeuroWeave lifecycle smoke..."
& $startScript -ApiPort $ApiPort -WebPort $WebPort -NoBrowser
Assert-Health

Write-Host "Checking idempotent second start..."
& $startScript -ApiPort $ApiPort -WebPort $WebPort -NoBrowser
Assert-Health

if (-not (Test-Path $runtimeDir)) {
    throw "Runtime marker directory was not created under data/runtime."
}
$apiMarkerPath = Join-Path $runtimeDir "api-$ApiPort.json"
$webMarkerPath = Join-Path $runtimeDir "web-$WebPort.json"
foreach ($markerPath in @($apiMarkerPath, $webMarkerPath)) {
    if (-not (Test-Path $markerPath)) {
        throw "Expected runtime marker was not created: $markerPath"
    }
    $marker = Get-Content -Path $markerPath -Raw | ConvertFrom-Json
    if (-not (Test-Path $marker.logPath)) {
        throw "Runtime marker log path does not exist: $($marker.logPath)"
    }
    if (-not $marker.logPath.StartsWith($logsDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Runtime marker log path is outside data/logs: $($marker.logPath)"
    }
}

Write-Host "Stopping NeuroWeave lifecycle smoke..."
& $stopScript -Ports @($ApiPort, $WebPort)
Assert-RepoOwnedListenerStopped -Port $ApiPort
Assert-RepoOwnedListenerStopped -Port $WebPort

Write-Host "Lifecycle smoke complete."
