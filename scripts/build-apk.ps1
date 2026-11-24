param(
    [switch]$Release,
    [string]$ApiBase = ""
)

# بناء ملف APK من واجهة الويب باستخدام Capacitor
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$capDir = Join-Path $root "capacitor"
$androidDir = Join-Path $capDir "android"
$distDir = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm غير موجود. ثبّت Node.js LTS أولاً: scripts\install-build-tools.ps1"
}
if (-not (Get-Command java -ErrorAction SilentlyContinue) -and -not $env:JAVA_HOME) {
    throw "Java غير موجود. ثبّت JDK 21 (مطلوب لـ Capacitor 7) أو عيّن JAVA_HOME: scripts\install-build-tools.ps1"
}
if ($ApiBase) {
    $configJs = Join-Path $root "web\config.js"
    $apiLine = "window.TALABAT_API_BASE = `"$ApiBase`";"
    @("/* العنوان الافتراضي للسيرفر (يُضبط أثناء بناء APK). */", $apiLine) | Set-Content -Encoding utf8 $configJs
    Write-Host "رابط السيرفر داخل APK: $ApiBase"
}

Push-Location $capDir
try {
    Write-Host "1/4 تثبيت حزم Capacitor..."
    npm install --no-audit --no-fund

    if (-not (Test-Path $androidDir)) {
        Write-Host "2/4 إضافة منصة Android..."
        npx cap add android
    } else {
        Write-Host "2/4 منصة Android موجودة بالفعل."
    }

    $iconScript = Join-Path $root "web\generate-android-icons.ps1"
    if (Test-Path $iconScript) { & $iconScript }

    $sdk = $env:ANDROID_HOME
    if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
    if (-not $sdk) { $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
    if (-not (Test-Path $sdk)) {
        throw "لم يتم العثور على Android SDK في: $sdk — ثبّت أدوات البناء أو عيّن ANDROID_HOME"
    }
    $localProperties = Join-Path $androidDir "local.properties"
    "sdk.dir=$($sdk -replace '\\','/')" | Set-Content -Encoding ascii $localProperties

    Write-Host "3/4 مزامنة ملفات الواجهة..."
    npx cap sync android

    Write-Host "4/4 بناء الـ APK..."
    Push-Location $androidDir
    try {
        if ($Release) {
            .\gradlew.bat assembleRelease
            $source = Join-Path $androidDir "app\build\outputs\apk\release\app-release-unsigned.apk"
            $target = Join-Path $distDir "TalabatHome-release-unsigned.apk"
        } else {
            .\gradlew.bat assembleDebug
            $source = Join-Path $androidDir "app\build\outputs\apk\debug\app-debug.apk"
            $target = Join-Path $distDir "TalabatHome-debug.apk"
        }
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $source)) { throw "لم يتم إنتاج ملف APK في: $source" }
Copy-Item $source $target -Force
Write-Host ""
Write-Host "تم بنجاح ✅"
Write-Host "الملف: $target"
