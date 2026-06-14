# AI Desk Helper — .pkg 빌드 & 배포

테스터들에게 더블클릭으로 설치할 수 있는 macOS 인스톨러를 만든다.

## 한 번만 — 빌드 환경 준비

```bash
cd desktop-agent
uv sync --group dev    # PyInstaller 까지 포함된 환경
```

## 빌드

```bash
cd desktop-agent
./build-pkg/build.sh                # → dist/AIDeskHelper-0.1.0-arm64.pkg
VERSION=0.2.0 ./build-pkg/build.sh  # 버전 명시
```

산출물: `desktop-agent/build-pkg/dist/AIDeskHelper-${VERSION}-${ARCH}.pkg`

## 테스터에게 전달

산출된 `.pkg` 파일을 그대로 전달. 동봉 안내:

> **설치**
>
> 1. `AIDeskHelper-x.y.z-arm64.pkg` 더블클릭
> 2. **첫 실행 시 "확인되지 않은 개발자" 경고**가 뜨면:
>    - Finder 에서 파일 **우클릭 → 열기** → 경고 창에서 다시 **열기**
>    - 또는 시스템설정 → 개인정보 보호 및 보안 → "그래도 열기"
> 3. 마법사 진행 (관리자 비밀번호 입력 — LaunchAgent 등록 때문)
> 4. 설치 완료 후 자동 실행됨
>
> **확인**
> ```
> launchctl list | grep com.aidesk.agent
> tail -f ~/Library/Logs/aidesk-agent.err
> ```

## 빌드 산출물이 하는 일

| 단계 | 내용 |
|---|---|
| preinstall | 이미 떠 있는 Helper 가 있으면 `launchctl bootout` |
| payload 복사 | `/usr/local/bin/aidesk-helper` (PyInstaller 단일 바이너리)<br>`/usr/local/share/aidesk/hooks/aidesk-*.cjs` |
| postinstall | 콘솔 사용자 식별 → `~/Library/LaunchAgents/com.aidesk.agent.plist` 생성 → `launchctl bootstrap` |

## 미서명 빌드의 한계

- 첫 실행 시 macOS Gatekeeper 경고 발생 (위 안내로 우회)
- 정식 배포 단계엔 Apple Developer ID 로 `productsign` + `notarytool` 필요

## 트러블슈팅

| 증상 | 원인/해결 |
|---|---|
| `pyinstaller: command not found` | `uv sync --group dev` 빠뜨림 |
| 설치 후 helper 가 안 뜸 | `tail ~/Library/Logs/aidesk-agent.err` 확인. PATH 문제일 가능성 |
| `launchctl bootout: No such process` | 정상 — 처음 설치 시 흔함, 무시 |
| Intel Mac 에서 arm64 .pkg 거부 | arm64 Mac 에서 빌드한 바이너리는 Intel 에서 안 돈다. Intel 용은 Intel Mac (또는 Rosetta) 에서 별도 빌드 |
