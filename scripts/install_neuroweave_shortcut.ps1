param(
    [switch]$Desktop,
    [switch]$StartMenu,
    [string]$ShortcutDirectory
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$launcherScript = Join-Path $PSScriptRoot "start_neuroweave.ps1"
$appDataDir = Join-Path $repoRoot "data\app"
$iconPath = Join-Path $appDataDir "neuroweave.ico"
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

function Write-Status {
    param([string]$Message)
    Write-Host "[NeuroWeave] $Message"
}

function New-NeuroWeaveIcon {
    param([string]$Path)

    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null

    Add-Type -AssemblyName System.Drawing

    $bitmap = New-Object System.Drawing.Bitmap 256, 256
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    try {
        $background = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(16, 24, 32))
        $tealPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(79, 209, 197)), 16
        $orangePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(246, 173, 85)), 16
        $dotBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(247, 250, 252))

        $tealPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $tealPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $orangePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $orangePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

        $graphics.FillRectangle($background, 0, 0, 256, 256)
        $graphics.DrawBezier($tealPen, 40, 140, 72, 66, 96, 66, 128, 140)
        $graphics.DrawBezier($tealPen, 128, 140, 160, 214, 184, 214, 216, 140)
        $graphics.DrawBezier($orangePen, 40, 116, 72, 190, 96, 190, 128, 116)
        $graphics.DrawBezier($orangePen, 128, 116, 160, 42, 184, 42, 216, 116)

        foreach ($x in @(64, 128, 192)) {
            $graphics.FillEllipse($dotBrush, $x - 10, 118, 20, 20)
        }

        $iconHandle = $bitmap.GetHicon()
        $icon = [System.Drawing.Icon]::FromHandle($iconHandle)
        $stream = [System.IO.File]::Create($Path)
        try {
            $icon.Save($stream)
        }
        finally {
            $stream.Dispose()
            $icon.Dispose()
        }
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-NeuroWeaveShortcut {
    param([string]$Directory)

    New-Item -ItemType Directory -Path $Directory -Force | Out-Null

    $shortcutPath = Join-Path $Directory "NeuroWeave.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershellExe
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherScript`" -ServerWindowStyle Hidden"
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.IconLocation = $iconPath
    $shortcut.Description = "Start NeuroWeave"
    $shortcut.WindowStyle = 7
    $shortcut.Save()

    Write-Status "Shortcut created: $shortcutPath"
}

if (-not $Desktop -and -not $StartMenu -and -not $ShortcutDirectory) {
    $Desktop = $true
    $StartMenu = $true
}

New-NeuroWeaveIcon -Path $iconPath
Write-Status "Icon ready: $iconPath"

if ($ShortcutDirectory) {
    New-NeuroWeaveShortcut -Directory $ShortcutDirectory
}

if ($Desktop) {
    New-NeuroWeaveShortcut -Directory ([Environment]::GetFolderPath("DesktopDirectory"))
}

if ($StartMenu) {
    New-NeuroWeaveShortcut -Directory (Join-Path ([Environment]::GetFolderPath("Programs")) "NeuroWeave")
}
