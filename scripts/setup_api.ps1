param(
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$venvDir = Join-Path $apiDir ".venv"
$requirements = Join-Path $apiDir "requirements.txt"

function Get-PythonInfo {
    param([string]$PythonExe)

    if (-not (Test-Path $PythonExe)) {
        return $null
    }

    $script = @"
import platform
import sys
import sysconfig

print(sys.executable)
print(platform.python_implementation())
print(sys.version_info.major)
print(sys.version_info.minor)
print(sysconfig.get_platform())
"@

    try {
        $output = & $PythonExe -c $script
        if ($output.Count -lt 5) {
            return $null
        }
        return [pscustomobject]@{
            executable = $output[0]
            implementation = $output[1]
            major = [int]$output[2]
            minor = [int]$output[3]
            platform = $output[4]
        }
    }
    catch {
        return $null
    }
}

function Test-SupportedPython {
    param($Info)

    if ($null -eq $Info) {
        return $false
    }

    if ($Info.implementation -ne "CPython") {
        return $false
    }

    if ($Info.major -ne 3 -or $Info.minor -lt 12 -or $Info.minor -gt 13) {
        return $false
    }

    if ($Info.platform -match "mingw" -or $Info.executable -match "\\msys64\\") {
        return $false
    }

    return $true
}

$candidates = @()

if ($env:NEUROWEAVE_PYTHON) {
    $candidates += $env:NEUROWEAVE_PYTHON
}

$candidates += @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
)

$python = $null
$pythonInfo = $null

foreach ($candidate in $candidates) {
    $info = Get-PythonInfo $candidate
    if (Test-SupportedPython $info) {
        $python = $candidate
        $pythonInfo = $info
        break
    }
}

if ($null -eq $python) {
    throw "No supported CPython found. Install CPython 3.12 or 3.13, or set NEUROWEAVE_PYTHON to python.exe."
}

if (Test-Path $venvDir) {
    $existingVenvPython = Join-Path $venvDir "Scripts\python.exe"
    $existingVenvInfo = Get-PythonInfo $existingVenvPython
    if ($Recreate -or -not (Test-SupportedPython $existingVenvInfo)) {
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
}

if ($Recreate -and (Test-Path $venvDir)) {
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path $venvDir)) {
    & $python -m venv $venvDir
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install -r $requirements

Write-Host "API environment ready."
Write-Host "Python: $($pythonInfo.executable)"
Write-Host "Virtualenv: $venvDir"
