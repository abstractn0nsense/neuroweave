param(
    [string]$OutputPath = "dist\desktop\icon\neuroweave.ico"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedOutputPath = Join-Path $repoRoot $OutputPath

New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutputPath) -Force | Out-Null

Add-Type -AssemblyName System.Drawing

$bitmap = New-Object System.Drawing.Bitmap 256, 256
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

try {
    $background = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(15, 20, 26))
    $tealPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(102, 217, 239)), 16
    $goldPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(246, 196, 83)), 16
    $dotBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 255, 255))

    $tealPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $tealPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $goldPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $goldPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    $graphics.FillRectangle($background, 0, 0, 256, 256)
    $graphics.DrawBezier($tealPen, 44, 143, 76, 86, 99, 86, 111, 143)
    $graphics.DrawBezier($tealPen, 111, 143, 132, 201, 157, 201, 178, 143)
    $graphics.DrawBezier($tealPen, 178, 143, 190, 112, 201, 101, 212, 100)

    $graphics.DrawBezier($goldPen, 44, 113, 76, 170, 99, 170, 111, 113)
    $graphics.DrawBezier($goldPen, 111, 113, 132, 55, 157, 55, 178, 113)
    $graphics.DrawBezier($goldPen, 178, 113, 190, 144, 201, 155, 212, 156)
    $graphics.FillEllipse($dotBrush, 110, 110, 36, 36)

    $iconHandle = $bitmap.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($iconHandle)
    $stream = [System.IO.File]::Create($resolvedOutputPath)
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

Write-Host "Desktop icon created: $resolvedOutputPath"
