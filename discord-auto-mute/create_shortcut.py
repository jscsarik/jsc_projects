import os
import win32com.client

def create_shortcut():
    # 현재 스크립트 위치 기준 설정 (DiscordAutoMute 폴더 내에 생성)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    shortcut_path = os.path.join(current_dir, 'Discord Canary (음성인식).lnk')
    target_path = os.path.join(current_dir, "launcher.vbs")
    working_dir = current_dir

    # 디스코드 아이콘 가져오기 (Canary 우선 탐색)
    canary_dir = os.path.join(os.environ['LOCALAPPDATA'], "DiscordCanary")
    discord_dir = os.path.join(os.environ['LOCALAPPDATA'], "Discord")
    
    if os.path.exists(os.path.join(canary_dir, "Update.exe")):
        icon_path = os.path.join(canary_dir, "Update.exe")
    elif os.path.exists(os.path.join(discord_dir, "Update.exe")):
        icon_path = os.path.join(discord_dir, "Update.exe")
    else:
        icon_path = target_path
    
    shell = win32com.client.Dispatch("WScript.Shell")
    
    # Discord Canary (음성인식) 바로가기 생성
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = target_path
    shortcut.WorkingDirectory = working_dir
    shortcut.WindowStyle = 1
    shortcut.IconLocation = f"{icon_path},0"
    shortcut.save()

    print(f"폴더 내에 '{shortcut_path}' 바로가기가 성공적으로 생성되었습니다!")

if __name__ == "__main__":
    create_shortcut()
