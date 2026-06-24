"""AI Desk Helper (Windows) 자체추출 설치기 — 단일 setup.exe.

macOS .pkg 대응. 더블클릭하면:
  - 번들된 payload.zip 을 %LOCALAPPDATA%\\AIDeskHelper 로 추출
  - 로그인 시 자동시작 등록 (작업 스케줄러, ONLOGON, 숨김 실행)
  - "프로그램 추가/제거" 항목 등록 (HKCU Uninstall)
  - helper 즉시 백그라운드 실행
실행 인자 `--uninstall` 이면 위를 역으로 제거.

PyInstaller onefile + windowed(console=False) 로 빌드. 진행/결과는 MessageBox.
payload.zip 은 _MEIPASS 안에 datas 로 동봉되며, 루트에 win-helper.exe / adesk-cli /
aidesk-channel 가 곧바로 위치한다 (top folder 없음).
"""
import ctypes
import os
import subprocess
import sys
import time
import winreg
import zipfile

APP_NAME = "AI Desk Helper"
APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "AIDeskHelper")
HELPER_EXE = os.path.join(APP_DIR, "win-helper.exe")
UNINSTALL_EXE = os.path.join(APP_DIR, "uninstall.exe")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AIDeskHelper"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDeskHelper"
VERSION = "0.8.13"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

MB_OK = 0x0
MB_ICONINFO = 0x40
MB_ICONWARN = 0x30
MB_ICONERROR = 0x10


def msg(text: str, flags: int = MB_ICONINFO) -> None:
    # --silent (CI/검증) 면 MessageBox 대신 로그로만 — blocking 다이얼로그 회피.
    # windowed(.exe) 에선 sys.stderr 가 None 이라 직접 쓰면 깨짐 → 가드.
    if "--silent" in sys.argv:
        try:
            (sys.stderr or sys.stdout).write(f"[AIDeskHelper] {text}\n")
        except Exception:  # noqa: BLE001 — None.write 등
            pass
        return
    ctypes.windll.user32.MessageBoxW(0, text, APP_NAME, flags)


def run_hidden(args, timeout: int = 30) -> subprocess.CompletedProcess:
    """콘솔 창 없이 실행. 실패해도 예외 안 던지고 결과만 반환."""
    return subprocess.run(
        args,
        creationflags=CREATE_NO_WINDOW,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _meipass() -> str:
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def kill_helper() -> None:
    run_hidden(["taskkill", "/IM", "win-helper.exe", "/F"])


def set_autostart() -> None:
    # HKCU Run 키 — 권한 불필요(비관리자 OK), 로그인 시 자동시작.
    # win-helper.exe 는 windowed(console=False) 라 콘솔창이 뜨지 않는다.
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, f'"{HELPER_EXE}"')


def remove_autostart() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_VALUE)
    except FileNotFoundError:
        pass


def start_helper() -> None:
    # 즉시 백그라운드 실행 — windowed exe 라 창 없음.
    subprocess.Popen(
        [HELPER_EXE],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
        cwd=APP_DIR,
    )


def write_uninstall_registry() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
        winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "Kaflix")
        winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, APP_DIR)
        winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, HELPER_EXE)
        winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{UNINSTALL_EXE}" --uninstall')
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def remove_uninstall_registry() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass


def rmtree_retry(path: str, attempts: int = 5) -> None:
    import shutil
    for i in range(attempts):
        if not os.path.isdir(path):
            return
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.5)


def install() -> None:
    import shutil

    payload = os.path.join(_meipass(), "payload.zip")
    if not os.path.isfile(payload):
        msg(f"설치 페이로드를 찾을 수 없습니다:\n{payload}", MB_ICONERROR)
        sys.exit(1)

    node_ok = shutil.which("node") is not None

    # 기존 helper 중지
    kill_helper()
    time.sleep(0.5)

    # 기존 설치 정리 (uninstall.exe 가 안 잡히게 helper 만 죽인 뒤 통째 삭제)
    rmtree_retry(APP_DIR)
    os.makedirs(APP_DIR, exist_ok=True)

    # 페이로드 추출
    with zipfile.ZipFile(payload) as z:
        z.extractall(APP_DIR)
    if not os.path.isfile(HELPER_EXE):
        msg(f"win-helper.exe 가 페이로드에 없습니다:\n{HELPER_EXE}", MB_ICONERROR)
        sys.exit(1)

    # 제거용으로 설치기 자신을 복사
    try:
        shutil.copy2(sys.executable, UNINSTALL_EXE)
    except OSError:
        pass

    set_autostart()
    write_uninstall_registry()
    start_helper()

    extra = "" if node_ok else (
        "\n\n⚠️ Node.js 가 감지되지 않았습니다.\n"
        "메시지 채널(MCP)·사용량 표시가 동작하려면 https://nodejs.org 의 LTS 를\n"
        "설치한 뒤 PC 를 재로그인하거나 helper 를 재시작하세요."
    )
    msg(
        f"{APP_NAME} 설치가 완료되었습니다.\n\n"
        f"설치 위치: {APP_DIR}\n"
        f"helper 가 백그라운드로 실행 중이며 다음 로그인부터 자동 시작됩니다.\n"
        f"대시보드로 돌아가 '설치 완료 — 다시 확인' 을 눌러주세요." + extra
    )


def uninstall() -> None:
    remove_autostart()
    kill_helper()
    remove_uninstall_registry()
    time.sleep(0.3)

    # uninstall.exe(=현재 실행 중 프로세스)는 자기 자신을 못 지우므로,
    # 분리된 cmd 가 프로세스 종료를 기다렸다 APP_DIR 통째 삭제.
    subprocess.Popen(
        f'cmd /c ping 127.0.0.1 -n 3 >nul & rmdir /s /q "{APP_DIR}"',
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
    )
    msg(f"{APP_NAME} 가 제거되었습니다.")


def main() -> None:
    if "--uninstall" in sys.argv:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — 설치기는 어떤 예외든 사용자에게 보여야 함
        msg(f"오류가 발생했습니다:\n{e}", MB_ICONERROR)
        sys.exit(1)
