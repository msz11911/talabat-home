# تحضير أدوات بناء APK على Windows
$ErrorActionPreference = "Stop"

Write-Host "1/3 Node.js LTS..."
winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements

Write-Host "2/3 Java 21 (مطلوب لـ Capacitor 7 / Android Gradle Plugin)..."
winget install --id EclipseAdoptium.Temurin.21.JDK --accept-source-agreements --accept-package-agreements

Write-Host "3/3 Android SDK command-line tools..."
$sdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$cmdlineDir = Join-Path $sdkRoot "cmdline-tools"
$latestDir = Join-Path $cmdlineDir "latest"
if (-not (Test-Path (Join-Path $latestDir "bin\sdkmanager.bat"))) {
    $zip = Join-Path $env:TEMP "commandlinetools-win.zip"
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile $zip
    New-Item -ItemType Directory -Force -Path $latestDir | Out-Null
    Expand-Archive -Path $zip -DestinationPath $cmdlineDir -Force
    Move-Item -Path (Join-Path $cmdlineDir "cmdline-tools\*") -Destination $latestDir -Force
}

$env:ANDROID_HOME = $sdkRoot
$sdkManager = Join-Path $latestDir "bin\sdkmanager.bat"
& $sdkManager --sdk_root=$sdkRoot "platform-tools" "platforms;android-35" "build-tools;35.0.0" "build-tools;34.0.0"

Write-Host ""
Write-Host "انتهى. أغلق الطرفية وافتحها من جديد ثم شغّل: scripts\build-apk.ps1"
Write-Host "إن فضّلت طريقة أسهل، ثبّت Android Studio من: https://developer.android.com/studio"
