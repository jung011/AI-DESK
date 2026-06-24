# AI Desk Helper (Windows) 빌드 — PyInstaller .exe + 배포 .zip
#   macOS build.sh 의 Windows 대응. 산출물: desktop-agent/dist-win/AIDeskHelper-win.zip
# 실행: powershell -ExecutionPolicy Bypass -File build-pkg-win/build.ps1
$ErrorActionPreference = "Stop"
$DA = Split-Path $PSScriptRoot -Parent          # desktop-agent
$ROOT = Split-Path $DA -Parent                  # repo root
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = "$env:APPDATA\Python\Python314\Scripts\uv.exe" }

Write-Host "[1/3] PyInstaller build" -ForegroundColor Cyan
Push-Location $DA
& $uv run pyinstaller build-pkg-win/win-helper.spec --noconfirm --distpath dist-win --workpath build-win
Pop-Location
$exe = Join-Path $DA "dist-win\win-helper.exe"
if (-not (Test-Path $exe)) { throw "build 실패: $exe 없음" }

Write-Host "[2/3] 패키지 staging (exe + node 스크립트 + installer)" -ForegroundColor Cyan
$stage = Join-Path $DA "build-win\pkg\AIDeskHelper"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $stage "adesk-cli\bin") -Force | Out-Null
Copy-Item $exe $stage
Copy-Item (Join-Path $ROOT "adesk-cli\bin\aidesk-statusline.cjs") (Join-Path $stage "adesk-cli\bin")
# aidesk-channel MCP — node_modules 포함 (node 로 실행되므로 deps 필요)
Copy-Item (Join-Path $ROOT "aidesk-channel") (Join-Path $stage "aidesk-channel") -Recurse
Copy-Item (Join-Path $PSScriptRoot "install.ps1") $stage

Write-Host "[3/3] zip" -ForegroundColor Cyan
$zip = Join-Path $DA "dist-win\AIDeskHelper-win.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Write-Host "완료 → $zip" -ForegroundColor Green
Get-Item $zip | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}} | Format-Table

# backend 가 서빙하는 helper-pkg 로 복사 → /api/helper/download?os=win 즉시 반영.
# Dockerfile 의 `COPY helper-pkg /app/helper` 로 prod image 에도 baked.
$served = Join-Path $ROOT "backend-py\helper-pkg"
if (Test-Path $served) {
    Copy-Item $zip $served -Force
    Write-Host "served → $served\AIDeskHelper-win.zip" -ForegroundColor Green
}
