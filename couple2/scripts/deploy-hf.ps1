# رفع المشروع إلى Hugging Face Spaces
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$git = "C:\Users\mohammed\AppData\Local\GitHubDesktop\app-3.7.0\resources\app\git\cmd\git.exe"
if (-not (Test-Path $git)) { $git = "git" }

Push-Location $root
try {
    $user = Read-Host "اسم مستخدم Hugging Face"
    $space = Read-Host "اسم الـ Space (اتركه فارغاً للافتراضي talabat-home)"
    if (-not $space) { $space = "talabat-home" }

    $secure = Read-Host "توكن الوصول (Write token) الذي يبدأ بـ hf_" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::FreeBSTR($bstr) }

    if (-not $token.StartsWith("hf_")) { throw "التوكن غير صحيح — يجب أن يبدأ بـ hf_" }

    $repo = "https://huggingface.co/spaces/$user/$space"

    Write-Host "جارٍ تحديث الـ commit المحلي..."
    & $git add -A
    & $git commit -m "Deploy to Hugging Face Spaces" 2>$null | Out-Null

    Write-Host "جارٍ الرفع إلى $repo ..."
    & $git remote remove hf 2>$null | Out-Null
    & $git remote add hf "$repo"
    & $git -c http.extraHeader="Authorization: Bearer $token" push hf main --force
    if ($LASTEXITCODE -ne 0) { throw "فشل الرفع. تأكد من اسم المستخدم وصلاحية التوكن (Write)." }

    & $git remote set-url hf "$repo"
    Write-Host ""
    Write-Host "تم الرفع بنجاح ✅"
    Write-Host "رابط الـ Space: $repo"
    Write-Host "بعد اكتمال البناء، اختبر: $repo/api/health"
} finally {
    Pop-Location
}
