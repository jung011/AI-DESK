# AI Desk Helper (Windows) 설치 스크립트
#   - %LOCALAPPDATA%\AIDeskHelper 로 복사
#   - 로그인 시 자동 시작 등록 (작업 스케줄러, ONLOGON)
#   - 즉시 백그라운드 실행
# 실행: 우클릭 → "PowerShell에서 실행"  또는
#       powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$dst = Join-Path $env:LOCALAPPDATA "AIDeskHelper"
$taskName = "AIDeskHelper"

Write-Host "=== AI Desk Helper 설치 ===" -ForegroundColor Cyan

# Node.js 필수 확인
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warning "Node.js 가 설치돼 있지 않습니다. helper 의 메시지 채널·사용량 표시가 동작하지 않습니다."
    Write-Warning "https://nodejs.org 에서 LTS 설치 후 다시 실행하세요. (설치는 계속 진행합니다)"
} else {
    Write-Host "Node.js 확인: $(node -v)" -ForegroundColor Green
}

# 기존 helper 중지 + 기존 작업 제거
Get-Process win-helper -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
schtasks /Delete /TN $taskName /F 2>$null | Out-Null

# 복사 (install.ps1 자신은 제외)
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Get-ChildItem -Path $src -Exclude "install.ps1" | Copy-Item -Destination $dst -Recurse -Force
$exe = Join-Path $dst "win-helper.exe"
if (-not (Test-Path $exe)) { throw "win-helper.exe 가 패키지에 없습니다: $exe" }

# 로그인 시 자동 시작 (작업 스케줄러)
schtasks /Create /TN $taskName /TR "`"$exe`"" /SC ONLOGON /RL LIMITED /F | Out-Null

# 지금 백그라운드 실행
Start-Process -FilePath $exe -WindowStyle Hidden

Write-Host "설치 완료 → $dst" -ForegroundColor Green
Write-Host "helper 가 백그라운드로 실행 중이며, 다음 로그인부터 자동 시작됩니다." -ForegroundColor Green
Write-Host "대시보드로 돌아가 '설치 완료 — 다시 확인' 을 눌러주세요."
