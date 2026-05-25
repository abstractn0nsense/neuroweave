param(
    [string]$OutputDir = "dist\desktop\backend",
    [string]$WorkDir = "data\cache\pyinstaller-work",
    [string]$SpecDir = "data\cache\pyinstaller-spec",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $repoRoot "apps\api"
$python = Join-Path $apiDir ".venv\Scripts\python.exe"
$entrypoint = Join-Path $apiDir "desktop_backend.py"
$resolvedOutputDir = Join-Path $repoRoot $OutputDir
$resolvedWorkDir = Join-Path $repoRoot $WorkDir
$resolvedSpecDir = Join-Path $repoRoot $SpecDir

if (-not (Test-Path $python)) {
    throw "API virtual environment was not found at $python. Run scripts/setup_api.ps1 first."
}

if (-not (Test-Path $entrypoint)) {
    throw "Backend entrypoint was not found at $entrypoint."
}

if (-not $SkipDependencyInstall) {
    & $python -m pip install "pyinstaller>=6,<7"
}

New-Item -ItemType Directory -Path $resolvedOutputDir -Force | Out-Null
New-Item -ItemType Directory -Path $resolvedWorkDir -Force | Out-Null
New-Item -ItemType Directory -Path $resolvedSpecDir -Force | Out-Null

$paths = @(
    (Join-Path $repoRoot "apps\api"),
    (Join-Path $repoRoot "packages\eeg-core\src"),
    (Join-Path $repoRoot "packages\eeg-io\src"),
    (Join-Path $repoRoot "packages\eeg-processing\src")
)

$pyinstallerArgs = @(
    "-m", "PyInstaller",
    $entrypoint,
    "--name", "neuroweave-api",
    "--onefile",
    "--noconfirm",
    "--clean",
    "--distpath", $resolvedOutputDir,
    "--workpath", $resolvedWorkDir,
    "--specpath", $resolvedSpecDir,
    "--hidden-import", "main",
    "--hidden-import", "eeg_processing.worker_cli"
)

foreach ($pathValue in $paths) {
    $pyinstallerArgs += @("--paths", $pathValue)
}

& $python @pyinstallerArgs

$exePath = Join-Path $resolvedOutputDir "neuroweave-api.exe"
if (-not (Test-Path $exePath)) {
    throw "Backend executable was not created at $exePath."
}

Write-Host "Backend executable created: $exePath"
