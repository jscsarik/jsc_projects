"""
====================================================================
Super Mega Baseball 4 KBO 응원가 - 백그라운드 자동 실행기 (Auto Launcher)
====================================================================
- 백그라운드에서 supermegabaseball.exe 실행을 지속적으로 감지합니다.
- 게임이 켜지면 -> 'main.py' (응원가 플레이어) 자동 실행
- 게임이 종료되면 -> 'main.py' 자동 종료
- Windows 시작 프로그램(shell:startup)에 넣어두면 컴퓨터를 켤 때부터 완전 자동 동작!
====================================================================
"""

import os
import sys
import time
import subprocess
import psutil

TARGET_PROCESS = "supermegabaseball.exe"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(SCRIPT_DIR, "main.py")


def is_game_running() -> bool:
    """supermegabaseball.exe 실행 여부 확인"""
    for p in psutil.process_iter(['name']):
        try:
            if p.info['name'] and p.info['name'].lower() == TARGET_PROCESS:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def is_main_running() -> bool:
    """main.py가 이미 실행 중인지 확인"""
    for p in psutil.process_iter(['cmdline']):
        try:
            cmd = p.info.get('cmdline')
            if cmd and any("main.py" in str(arg) for arg in cmd):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def main():
    player_proc = None
    was_game_running = False

    while True:
        try:
            game_running = is_game_running()

            if game_running and not was_game_running:
                # 게임 시작 감지 -> main.py 자동 실행
                if not is_main_running():
                    player_proc = subprocess.Popen(
                        ["pythonw", MAIN_SCRIPT],
                        cwd=SCRIPT_DIR,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                was_game_running = True

            elif not game_running and was_game_running:
                # 게임 종료 감지 -> main.py 자동 종료
                if player_proc and player_proc.poll() is None:
                    try:
                        player_proc.terminate()
                    except Exception:
                        pass
                    player_proc = None
                else:
                    # 혹시 다른 프로세스로 떠있는 main.py가 있다면 함께 정리
                    for p in psutil.process_iter(['cmdline']):
                        try:
                            cmd = p.info.get('cmdline')
                            if cmd and any("main.py" in str(arg) for arg in cmd):
                                p.terminate()
                        except Exception:
                            pass
                was_game_running = False

        except Exception:
            pass

        # 1.5초마다 가볍게 체크 (CPU 사용률 0% 수준)
        time.sleep(1.5)


if __name__ == "__main__":
    main()
