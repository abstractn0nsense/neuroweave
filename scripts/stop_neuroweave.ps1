param(
    [int[]]$Ports = @(8000, 5173)
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

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

foreach ($port in $Ports) {
    Stop-NeuroWeavePort -Port $port
}

Write-Status "Stop command completed."
