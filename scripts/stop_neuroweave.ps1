param(
    [int[]]$Ports = @(8000, 5173)
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot "data\runtime"

function Write-Status {
    param([string]$Message)
    Write-Host "[NeuroWeave] $Message"
}

function Stop-NeuroWeavePort {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Status "No listener found on port $Port."
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($null -eq $processInfo) {
            continue
        }

        $commandLine = $processInfo.CommandLine
        $normalizedCommandLine = if ($commandLine) { $commandLine.ToLowerInvariant() } else { "" }
        $normalizedRepoRoot = $repoRoot.ToLowerInvariant()
        if ($normalizedCommandLine.Contains($normalizedRepoRoot)) {
            Stop-Process -Id $processId -Force
            Write-Status "Stopped PID $processId on port $Port."
        }
        else {
            Write-Status "Skipped PID $processId on port $Port because it does not appear to belong to this checkout."
        }
    }
}

function Stop-RuntimeMarkerProcess {
    param([System.IO.FileInfo]$MarkerFile)

    try {
        $marker = Get-Content -Path $MarkerFile.FullName -Raw | ConvertFrom-Json
    }
    catch {
        Write-Status "Removing unreadable runtime marker $($MarkerFile.Name)."
        Remove-Item -LiteralPath $MarkerFile.FullName -Force
        return
    }

    $processId = [int]$marker.pid
    if ($processId -le 0) {
        Remove-Item -LiteralPath $MarkerFile.FullName -Force
        return
    }

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo) {
        Write-Status "Runtime marker $($MarkerFile.Name) points to a stopped process."
        Remove-Item -LiteralPath $MarkerFile.FullName -Force
        return
    }

    $commandLine = if ($processInfo.CommandLine) { $processInfo.CommandLine.ToLowerInvariant() } else { "" }
    $normalizedRepoRoot = $repoRoot.ToLowerInvariant()
    if ($commandLine.Contains($normalizedRepoRoot)) {
        Stop-Process -Id $processId -Force
        Write-Status "Stopped runtime marker PID $processId ($($MarkerFile.BaseName))."
    }
    else {
        Write-Status "Skipped marker PID $processId because it does not appear to belong to this checkout."
    }

    Remove-Item -LiteralPath $MarkerFile.FullName -Force
}

if (Test-Path $runtimeDir) {
    Get-ChildItem -Path $runtimeDir -Filter "*.json" -File | ForEach-Object {
        Stop-RuntimeMarkerProcess -MarkerFile $_
    }
}

foreach ($port in $Ports) {
    Stop-NeuroWeavePort -Port $port
}

Write-Status "Stop command completed."
