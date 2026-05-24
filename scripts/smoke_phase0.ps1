param(
    [switch]$SkipWebInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiPython = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"
$webDir = Join-Path $repoRoot "apps\web"
$cacheDir = Join-Path $repoRoot "data\cache"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $repoRoot
    )

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Resolve-Npm {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npmCommand) {
        return $npmCommand.Source
    }

    $programFilesNpm = "C:\Program Files\nodejs\npm.cmd"
    if (Test-Path $programFilesNpm) {
        return $programFilesNpm
    }

    throw "npm.cmd was not found. Install Node.js LTS, then retry."
}

Set-Location $repoRoot
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

Write-Host "Setting up API environment..."
Invoke-Checked "powershell" @(
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    (Join-Path $repoRoot "scripts\setup_api.ps1")
)

Write-Host "Generating sample EEG files..."
Invoke-Checked $apiPython @((Join-Path $repoRoot "scripts\generate_sample_eeg.py"))

Write-Host "Running API/package tests..."
Invoke-Checked $apiPython @(
    "-m",
    "pytest",
    "tests",
    "-o",
    "cache_dir=data/cache/pytest-cache"
)

Write-Host "Checking API endpoints with TestClient..."
$apiCheckPath = Join-Path $cacheDir "phase0_api_smoke.py"
$apiCheck = @"
from pathlib import Path
import sys

sys.path.insert(0, r"$repoRoot")

from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)
health = client.get("/health")
health.raise_for_status()
samples = client.get("/datasets/samples")
samples.raise_for_status()
sample_items = samples.json()["samples"]
assert sample_items, "Expected at least one sample dataset"
metadata = client.get(f"/datasets/samples/{sample_items[0]['id']}/metadata")
metadata.raise_for_status()
print("API smoke check ok")
"@
Set-Content -Path $apiCheckPath -Value $apiCheck -Encoding UTF8
Invoke-Checked $apiPython @($apiCheckPath)

Write-Host "Checking web build..."
$npm = Resolve-Npm
$env:PATH = "C:\Program Files\nodejs;$env:PATH"

if (-not $SkipWebInstall -and -not (Test-Path (Join-Path $webDir "node_modules"))) {
    Invoke-Checked $npm @("install") $webDir
}

Invoke-Checked $npm @("run", "build") $webDir

Write-Host "Phase 0 smoke check complete."
