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
$apiPython = Join-Path $apiDir ".venv\Scripts\python.exe"
$setupScript = Join-Path $PSScriptRoot "setup_api.ps1"
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
}

New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

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

if (Test-Url $apiUrl) {
    Write-Status "API is already running at $apiUrl"
}
else {
    if (Test-Path $apiLog) {
        Remove-Item -LiteralPath $apiLog -Force
    }

    $apiDirLiteral = ConvertTo-PowerShellLiteral $apiDir
    $apiPythonLiteral = ConvertTo-PowerShellLiteral $apiPython
    $apiLogLiteral = ConvertTo-PowerShellLiteral $apiLog
    $apiCommand = @"
Set-Location -LiteralPath $apiDirLiteral
& $apiPythonLiteral -m uvicorn main:app --reload --host 127.0.0.1 --port $ApiPort *> $apiLogLiteral
"@
    Start-LoggedPowerShell -Name "API" -Command $apiCommand
    Wait-ForUrl -Name "API" -Url $apiUrl -TimeoutSeconds $HealthTimeoutSeconds
}

if (Test-Url $webUrl) {
    Write-Status "Web app is already running at $webUrl"
}
else {
    if (Test-Path $webLog) {
        Remove-Item -LiteralPath $webLog -Force
    }

    $npmCommand = Get-NpmCommand
    $webDirLiteral = ConvertTo-PowerShellLiteral $webDir
    $npmCommandLiteral = ConvertTo-PowerShellLiteral $npmCommand
    $webLogLiteral = ConvertTo-PowerShellLiteral $webLog
    $webCommand = @"
Set-Location -LiteralPath $webDirLiteral
& $npmCommandLiteral run dev -- --host 127.0.0.1 --port $WebPort *> $webLogLiteral
"@
    Start-LoggedPowerShell -Name "Web" -Command $webCommand
    Wait-ForUrl -Name "Web app" -Url $webUrl -TimeoutSeconds $HealthTimeoutSeconds
}

if (-not $NoBrowser) {
    Write-Status "Opening $webUrl"
    Start-Process $webUrl
}

Write-Status "NeuroWeave is ready."
Write-Status "Logs: $logsDir"
