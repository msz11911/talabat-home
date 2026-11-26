# Generate Android launcher icons from web/icons/icon-512.png (run after cap add android)
Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $PSScriptRoot "icons\icon-512.png"
$resDir = Join-Path $root "capacitor\android\app\src\main\res"
if (-not (Test-Path $source)) { throw "Source image not found: $source" }
if (-not (Test-Path $resDir)) { throw "Android project not found. Run scripts\build-apk.ps1 first." }

$sizes = @{
  "mipmap-mdpi" = @{ launcher = 48; round = 48; foreground = 108 }
  "mipmap-hdpi" = @{ launcher = 72; round = 72; foreground = 162 }
  "mipmap-xhdpi" = @{ launcher = 96; round = 96; foreground = 216 }
  "mipmap-xxhdpi" = @{ launcher = 144; round = 144; foreground = 324 }
  "mipmap-xxxhdpi" = @{ launcher = 192; round = 192; foreground = 432 }
}

$original = [System.Drawing.Image]::FromFile($source)
try {
  foreach ($folder in $sizes.Keys) {
    $dir = Join-Path $resDir $folder
    if (-not (Test-Path $dir)) { continue }
    foreach ($kind in @("launcher", "round", "foreground")) {
      $size = [int]$sizes[$folder][$kind]
      $bitmap = New-Object System.Drawing.Bitmap($size, $size)
      $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
      $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
      $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $graphics.Clear([System.Drawing.Color]::Transparent)
      $graphics.DrawImage($original, 0, 0, $size, $size)
      $name = if ($kind -eq "launcher") { "ic_launcher.png" } elseif ($kind -eq "round") { "ic_launcher_round.png" } else { "ic_launcher_foreground.png" }
      $bitmap.Save((Join-Path $dir $name), [System.Drawing.Imaging.ImageFormat]::Png)
      $graphics.Dispose()
      $bitmap.Dispose()
    }
    Write-Host "Icons: $folder"
  }
} finally {
  $original.Dispose()
}
Write-Host "Android icons updated."
