param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [int]$HealthTimeoutSeconds = 90,
    [ValidateSet("Hidden", "Minimized", "Normal")]
    [string]$ServerWindowStyle = "Hidden",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$webDir = Join-Path $repoRoot "apps\web"
$logsDir = Join-Path $repoRoot "data\logs"
$runtimeDir = Join-Path $repoRoot "data\runtime"
$apiPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$setupScript = Join-Path $PSScriptRoot "setup_api.ps1"
$stopScript = Join-Path $PSScriptRoot "stop_neuroweave.ps1"
$apiUrl = "http://127.0.0.1:$ApiPort/health"
$webUrl = "http://127.0.0.1:$WebPort"

function Write-Status {
    param([string]$Message)
    Write-Host "[NeuroWeave] $Message"
}

function Test-Url {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

function Test-ApiHealth {
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -TimeoutSec 2
        return $response.status -eq "ok" -and $response.service -eq "neuroweave-api"
    }
    catch {
        return $false
    }
}

function Get-ListenerProcessIds {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Test-RepoOwnedProcessId {
    param([int]$ProcessId)

    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $processInfo -or -not $processInfo.CommandLine) {
        return $false
    }

    return $processInfo.CommandLine.ToLowerInvariant().Contains($repoRoot.ToLowerInvariant())
}

function Assert-PortAvailableOrOwned {
    param(
        [string]$Name,
        [int]$Port,
        [bool]$Healthy
    )

    $processIds = @(Get-ListenerProcessIds -Port $Port)
    if ($processIds.Count -eq 0) {
        return
    }

    $repoOwnedIds = @($processIds | Where-Object { Test-RepoOwnedProcessId -ProcessId $_ })
    if ($Healthy -and $repoOwnedIds.Count -gt 0) {
        Write-Status "$Name is already running on port $Port with repo-owned PID(s): $($repoOwnedIds -join ', ')."
        return
    }

    if ($repoOwnedIds.Count -gt 0) {
        Write-Status "$Name has stale repo-owned listener(s) on port $Port; stopping them first."
        & $stopScript -Ports @($Port)
        Wait-ForPortClosed -Name $Name -Port $Port -TimeoutSeconds 15
        return
    }

    throw "$Name port $Port is already used by non-NeuroWeave PID(s): $($processIds -join ', '). Stop that process or choose another port."
}

function Wait-ForPortClosed {
    param(
        [string]$Name,
        [int]$Port,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (@(Get-ListenerProcessIds -Port $Port).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 250
    }

    throw "$Name port $Port did not close within $TimeoutSeconds seconds."
}

function Wait-ForUrl {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $Url) {
            Write-Status "$Name is ready at $Url"
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "$Name did not become ready at $Url within $TimeoutSeconds seconds."
}

function Get-NpmCommand {
    $npm = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -ne $npm) {
        return $npm.Source
    }

    $npm = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($null -ne $npm) {
        return $npm.Source
    }

    throw "npm was not found. Install Node.js LTS before starting the web app."
}

function ConvertTo-PowerShellLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Start-LoggedPowerShell {
    param(
        [string]$Name,
        [string]$Command
    )

    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    $process = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand) `
        -WindowStyle $ServerWindowStyle `
        -PassThru

    Write-Status "$Name started with PID $($process.Id)."
    return $process
}

function Write-RuntimeMarker {
    param(
        [string]$Name,
        [int]$Port,
        [int]$ProcessId,
        [string]$LogPath
    )

    $marker = @{
        name = $Name
        port = $Port
        pid = $ProcessId
        repoRoot = $repoRoot
        logPath = $LogPath
        startedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    }
    $markerPath = Join-Path $runtimeDir "$($Name.ToLowerInvariant())-$Port.json"
    $marker | ConvertTo-Json -Depth 4 | Set-Content -Path $markerPath -Encoding UTF8
}

function Initialize-LogPath {
    param(
        [string]$Name,
        [int]$Port,
        [string]$PreferredPath
    )

    if (-not (Test-Path $PreferredPath)) {
        return $PreferredPath
    }

    try {
        Remove-Item -LiteralPath $PreferredPath -Force
        return $PreferredPath
    }
    catch {
        $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $fallbackPath = Join-Path $logsDir "$($Name.ToLowerInvariant())_$Port`_$stamp.log"
        Write-Status "$Name log is currently locked; writing this run to $fallbackPath"
        return $fallbackPath
    }
}

New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$setupLog = Join-Path $logsDir "setup_api.log"
$npmInstallLog = Join-Path $logsDir "npm_install.log"
$apiLog = Join-Path $logsDir "api.log"
$webLog = Join-Path $logsDir "web.log"

if (-not (Test-Path $apiPython)) {
    Write-Status "API environment is missing; running setup_api.ps1."
    & $setupScript *> $setupLog
}

if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
    Write-Status "Web dependencies are missing; running npm install."
    $npmCommand = Get-NpmCommand
    Push-Location $webDir
    try {
        & $npmCommand install *> $npmInstallLog
    }
    finally {
        Pop-Location
    }
}

Assert-PortAvailableOrOwned -Name "API" -Port $ApiPort -Healthy (Test-ApiHealth)
if (Test-ApiHealth) {
    Write-Status "API is already running at $apiUrl"
    $apiProcessId = @(Get-ListenerProcessIds -Port $ApiPort | Where-Object { Test-RepoOwnedProcessId -ProcessId $_ } | Select-Object -First 1)
    if ($apiProcessId.Count -gt 0) {
        Write-RuntimeMarker -Name "API" -Port $ApiPort -ProcessId $apiProcessId[0] -LogPath $apiLog
    }
}
else {
    $apiLog = Initialize-LogPath -Name "API" -Port $ApiPort -PreferredPath $apiLog

    $apiDirLiteral = ConvertTo-PowerShellLiteral $apiDir
    $apiPythonLiteral = ConvertTo-PowerShellLiteral $apiPython
    $apiLogLiteral = ConvertTo-PowerShellLiteral $apiLog
    $apiCommand = @"
Set-Location -LiteralPath $apiDirLiteral
& $apiPythonLiteral -m uvicorn main:app --reload --host 127.0.0.1 --port $ApiPort *> $apiLogLiteral
"@
    Start-LoggedPowerShell -Name "API" -Command $apiCommand | Out-Null
    Wait-ForUrl -Name "API" -Url $apiUrl -TimeoutSeconds $HealthTimeoutSeconds
    $apiProcessId = @(Get-ListenerProcessIds -Port $ApiPort | Where-Object { Test-RepoOwnedProcessId -ProcessId $_ } | Select-Object -First 1)
    if ($apiProcessId.Count -gt 0) {
        Write-RuntimeMarker -Name "API" -Port $ApiPort -ProcessId $apiProcessId[0] -LogPath $apiLog
    }
}

Assert-PortAvailableOrOwned -Name "Web app" -Port $WebPort -Healthy (Test-Url $webUrl)
if (Test-Url $webUrl) {
    Write-Status "Web app is already running at $webUrl"
    $webProcessId = @(Get-ListenerProcessIds -Port $WebPort | Where-Object { Test-RepoOwnedProcessId -ProcessId $_ } | Select-Object -First 1)
    if ($webProcessId.Count -gt 0) {
        Write-RuntimeMarker -Name "Web" -Port $WebPort -ProcessId $webProcessId[0] -LogPath $webLog
    }
}
else {
    $webLog = Initialize-LogPath -Name "Web" -Port $WebPort -PreferredPath $webLog

    $npmCommand = Get-NpmCommand
    $webDirLiteral = ConvertTo-PowerShellLiteral $webDir
    $npmCommandLiteral = ConvertTo-PowerShellLiteral $npmCommand
    $webLogLiteral = ConvertTo-PowerShellLiteral $webLog
    $webCommand = @"
Set-Location -LiteralPath $webDirLiteral
& $npmCommandLiteral run dev -- --host 127.0.0.1 --port $WebPort *> $webLogLiteral
"@
    Start-LoggedPowerShell -Name "Web" -Command $webCommand | Out-Null
    Wait-ForUrl -Name "Web app" -Url $webUrl -TimeoutSeconds $HealthTimeoutSeconds
    $webProcessId = @(Get-ListenerProcessIds -Port $WebPort | Where-Object { Test-RepoOwnedProcessId -ProcessId $_ } | Select-Object -First 1)
    if ($webProcessId.Count -gt 0) {
        Write-RuntimeMarker -Name "Web" -Port $WebPort -ProcessId $webProcessId[0] -LogPath $webLog
    }
}

if (-not $NoBrowser) {
    Write-Status "Opening $webUrl"
    Start-Process $webUrl
}

Write-Status "NeuroWeave is ready."
Write-Status "Logs: $logsDir"
Write-Status "Runtime markers: $runtimeDir"
