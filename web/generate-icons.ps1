# توليد أيقونات التطبيق (192 / 512) بدون مكتبات خارجية
Add-Type -AssemblyName System.Drawing

$iconDir = Join-Path $PSScriptRoot "icons"
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null

function New-AppIcon([int]$size) {
    $bitmap = New-Object System.Drawing.Bitmap($size, $size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $graphics.Clear([System.Drawing.Color]::Transparent)

    $c1 = [System.Drawing.Color]::FromArgb(255, 255, 168, 84)
    $c2 = [System.Drawing.Color]::FromArgb(255, 228, 88, 18)
    $gradient = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        (New-Object System.Drawing.Point(0, 0)),
        (New-Object System.Drawing.Point($size, $size)), $c1, $c2)

    $radius = [int]($size * 0.22)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddArc(0, 0, $radius, $radius, 180, 90)
    $path.AddArc($size - $radius, 0, $radius, $radius, 270, 90)
    $path.AddArc($size - $radius, $size - $radius, $radius, $radius, 0, 90)
    $path.AddArc(0, $size - $radius, $radius, $radius, 90, 90)
    $path.CloseFigure()
    $graphics.FillPath($gradient, $path)

    # حقيبة التسوق البيضاء
    $bagW = [int]($size * 0.46)
    $bagH = [int]($size * 0.40)
    $bagX = [int](($size - $bagW) / 2)
    $bagY = [int]($size * 0.36)
    $graphics.FillRectangle([System.Drawing.Brushes]::White, $bagX, $bagY, $bagW, $bagH)

    $penWidth = [Math]::Max(2, [int]($size * 0.035))
    $pen = New-Object System.Drawing.Pen([System.Drawing.Brushes]::White, $penWidth)
    $handleW = [int]($bagW * 0.48)
    $handleH = [int]($size * 0.17)
    $handleX = [int]($bagX + ($bagW - $handleW) / 2)
    $graphics.DrawArc($pen, $handleX, [int]($bagY - $handleH * 0.72), $handleW, $handleH, 180, 180)

    # نقطة صغيرة كلogo داخل الحقيبة
    $dot = [int]($size * 0.055)
    $graphics.FillEllipse($gradient, [int]($bagX + $bagW / 2 - $dot / 2), [int]($bagY + $bagH * 0.52 - $dot / 2), $dot, $dot)

    $target = Join-Path $iconDir "icon-$size.png"
    $bitmap.Save($target, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $pen.Dispose()
    $gradient.Dispose()
    $path.Dispose()
    $bitmap.Dispose()
    Write-Host "تم إنشاء: $target"
}

New-AppIcon 192
New-AppIcon 512
