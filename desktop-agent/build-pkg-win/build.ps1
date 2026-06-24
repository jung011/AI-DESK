# AI Desk Helper (Windows) 빌드 — PyInstaller helper.exe + 자체추출 setup.exe
#   macOS build.sh 의 Windows 대응. 산출물: desktop-agent/dist-win/AIDeskHelper-Setup.exe
# 실행: powershell -ExecutionPolicy Bypass -File build-pkg-win/build.ps1
$ErrorActionPreference = "Stop"
$DA = Split-Path $PSScriptRoot -Parent          # desktop-agent
$ROOT = Split-Path $DA -Parent                  # repo root
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = "$env:APPDATA\Python\Python314\Scripts\uv.exe" }

Write-Host "[1/4] helper.exe 빌드 (PyInstaller)" -ForegroundColor Cyan
Push-Location $DA
& $uv run pyinstaller build-pkg-win/win-helper.spec --noconfirm --distpath dist-win --workpath build-win
Pop-Location
$exe = Join-Path $DA "dist-win\win-helper.exe"
if (-not (Test-Path $exe)) { throw "build 실패: $exe 없음" }

Write-Host "[2/4] payload staging (exe + node 스크립트)" -ForegroundColor Cyan
# payload 루트에 곧바로 win-helper.exe / adesk-cli / aidesk-channel — top folder 없음.
$stage = Join-Path $DA "build-win\payload"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $stage "adesk-cli\bin") -Force | Out-Null
Copy-Item $exe $stage
Copy-Item (Join-Path $ROOT "adesk-cli\bin\aidesk-statusline.cjs") (Join-Path $stage "adesk-cli\bin")
# aidesk-channel MCP — node_modules 포함 (node 로 실행되므로 deps 필요)
Copy-Item (Join-Path $ROOT "aidesk-channel") (Join-Path $stage "aidesk-channel") -Recurse

Write-Host "[3/4] payload.zip (설치기 동봉용)" -ForegroundColor Cyan
$payload = Join-Path $DA "build-win\payload.zip"
if (Test-Path $payload) { Remove-Item $payload -Force }
# stage\* (내용물만) → 추출 시 top folder 없이 곧바로 위치.
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $payload -CompressionLevel Optimal

Write-Host "[4/4] AIDeskHelper-Setup.exe 빌드 (자체추출 설치기)" -ForegroundColor Cyan
Push-Location $DA
& $uv run pyinstaller build-pkg-win/win-installer.spec --noconfirm --distpath dist-win --workpath build-win
Pop-Location
$setup = Join-Path $DA "dist-win\AIDeskHelper-Setup.exe"
if (-not (Test-Path $setup)) { throw "build 실패: $setup 없음" }
Write-Host "완료 → $setup" -ForegroundColor Green
Get-Item $setup | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}} | Format-Table

# backend 가 서빙하는 helper-pkg 로 복사 → /api/helper/download?os=win 즉시 반영.
# Dockerfile 의 `COPY helper-pkg /app/helper` 로 prod image 에도 baked.
$served = Join-Path $ROOT "backend-py\helper-pkg"
if (Test-Path $served) {
    Get-ChildItem $served -Filter "AIDeskHelper-win.zip" -ErrorAction SilentlyContinue | Remove-Item -Force
    Copy-Item $setup $served -Force
    Write-Host "served → $served\AIDeskHelper-Setup.exe" -ForegroundColor Green
}
