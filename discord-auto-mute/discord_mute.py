import speech_recognition as sr
import keyboard
import time
import ctypes
import os
import psutil
import sys
import datetime
import pyaudio

class RollingLog:
    def __init__(self, filename, max_lines=100):
        self.filename = filename
        self.max_lines = max_lines
        self.line_count = 0
        self._check_initial_lines()

    def _check_initial_lines(self):
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8', errors='ignore') as f:
                    self.line_count = sum(1 for _ in f)
        except Exception:
            self.line_count = 0

    def write(self, data):
        try:
            with open(self.filename, 'a', encoding='utf-8', errors='ignore') as f:
                f.write(data)
            if '\n' in data:
                self.line_count += data.count('\n')
                if self.line_count > self.max_lines:
                    self._trim()
        except Exception:
            pass

    def _trim(self):
        try:
            with open(self.filename, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            if len(lines) > self.max_lines:
                with open(self.filename, 'w', encoding='utf-8', errors='ignore') as f:
                    f.writelines(lines[-self.max_lines:])
                self.line_count = self.max_lines
        except Exception:
            pass

    def flush(self):
        pass

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def ensure_single_instance():
    my_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == my_pid:
                continue
            name = (proc.info.get('name') or '').lower()
            cmdline = proc.info.get('cmdline') or []
            
            is_other = False
            if name == 'discord_mute.exe':
                is_other = True
            elif name in ('python.exe', 'pythonw.exe'):
                if any('discord_mute.py' in arg.lower() for arg in cmdline):
                    is_other = True
                
            if is_other:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [재시작] 기존 실행 중이던 discord_mute(PID {proc.info['pid']})를 종료하고 새로 시작합니다.")
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.5)

EXCLUDE_MIC_KEYWORDS = [
    'dualsense', 'controller', 'wireless controller', 
    'steam streaming', 'virtual desktop', 'stereo mix', 
    '스테레오 믹스', 'mapper', 'hands-free', 'handsfree'
]
PREFERRED_MIC_KEYWORDS = [
    'c270', 'webcam', 'logi', 'headset', '헤드셋', 
    'airpods', 'wh-1000xm', 'realtek', '마이크', 'microphone', 'mic'
]

def get_best_microphone():
    p = pyaudio.PyAudio()
    default_idx = None
    default_name = ""
    try:
        def_info = p.get_default_input_device_info()
        default_idx = def_info.get('index')
        default_name = def_info.get('name', '')
    except Exception:
        pass

    candidates = []
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info.get('maxInputChannels', 0) > 0 and info.get('hostApi') == 0:
                name = info.get('name', '')
                name_lower = name.lower()
                is_excluded = any(k in name_lower for k in EXCLUDE_MIC_KEYWORDS)
                is_preferred = any(k in name_lower for k in PREFERRED_MIC_KEYWORDS)
                candidates.append((i, name, is_preferred, is_excluded, (i == default_idx)))
        except Exception:
            pass
    p.terminate()

    # 1순위: 선호 장치(웹캠, 헤드셋 등) 중 제외 대상이 아닌 장치
    for idx, name, pref, excl, is_def in candidates:
        if pref and not excl:
            return idx, name

    # 2순위: 윈도우 기본 장치 (단, 패드/가상 마이크가 아닌 경우)
    if default_idx is not None:
        for idx, name, pref, excl, is_def in candidates:
            if is_def and not excl:
                return idx, name

    # 3순위: 제외 대상이 아닌 아무 입력 장치
    for idx, name, pref, excl, is_def in candidates:
        if not excl:
            return idx, name

    # 최후의 수단: 윈도우 기본 장치
    return default_idx, default_name or "기본 마이크"


DISCORD_PROCESS_NAMES = {
    'discord.exe': 'Discord',
    'discordcanary.exe': 'Discord Canary',
    'discordptb.exe': 'Discord PTB',
    'discorddevelopment.exe': 'Discord Development'
}

_last_discord_check = 0.0
_cached_discord_name = None

def get_running_discord_name(force=False):
    global _last_discord_check, _cached_discord_name
    now = time.time()
    if not force and (now - _last_discord_check < 3.0) and _cached_discord_name is not None:
        return _cached_discord_name

    _last_discord_check = now
    found = None
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info.get('name')
            if name:
                name_lower = name.lower()
                if name_lower in DISCORD_PROCESS_NAMES:
                    found = DISCORD_PROCESS_NAMES[name_lower]
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    _cached_discord_name = found
    return found

def is_discord_running():
    return get_running_discord_name() is not None

def send_discord_hotkey(hotkey_str):
    try:
        keys = [k.strip() for k in hotkey_str.split('+')]
        for k in keys:
            keyboard.press(k)
        time.sleep(0.08)  # 단축키가 씹히지 않도록 80ms 동안 누름 유지
        for k in reversed(keys):
            keyboard.release(k)
    except Exception:
        keyboard.send(hotkey_str)

# 키워드 전처리 (공백 제거 및 소문자화) - 매 루프마다 재계산하지 않고 1회만 계산
def _clean(kws):
    return tuple(kw.lower().replace(" ", "") for kw in kws)

MIC_OFF_DIRECT = _clean([
    "마이크오프", "마이크off", "마이크어프", "마이클오프", "마이클off", 
    "마이코프", "마이크어플", "michaelof", "michaeloff", "마익크",
    "마이크로폰오프", "마이크꺼", "마이크음소거", "아마이크오프", "마이크꺼줘",
    "마이크끄기", "마이크꺼봐", "마이크좀꺼줘", "마이크닫아", "음소거해줘", "음소거"
])
MIC_ON_DIRECT = _clean([
    "마이크온", "마이크on", "마이클온", "마이클on", "마이콘", 
    "마이크로폰온", "마이크켜", "마이크켜줘", "마이크온해줘", "마이크키기",
    "마이크켜봐", "마이크열어", "음소거해제", "음소거풀어"
])
MIC_KEYWORDS = _clean(["마이크", "마이클", "mic", "michael", "마코", "마이"])
OFF_KEYWORDS = _clean(["오프", "off", "of", "어플", "어프", "꺼", "음소거", "끄", "꺼줘", "닫아", "꺼봐"])
ON_KEYWORDS = _clean(["온", "on", "켜", "켜줘", "켜기", "키기", "풀어", "풀어줘", "열어", "켜봐"])
OFF_SOLO = _clean(["오프", "off", "어프", "of", "마이크", "마이클", "mic"])
ON_SOLO = _clean(["온", "on", "켜", "켜기", "키기"])

DISCONNECT_KEYWORDS = _clean([
    "좀있다옴", "좀잇다옴", "좀이따옴", "이따옴", "좀이따", "좀 있다",
    "연결끊기", "연결끊어", "채널나가기"
])
STREAM_OFF_KEYWORDS = _clean([
    "방송오프", "방송off", "방송종료", "방송꺼", "방송중단", "방송꺼줘", "방종", 
    "방송종료해", "화면공유종료", "화면공유꺼", "화공꺼", "화공종료", "화면공유끄기", "방송끄기"
])
STREAM_SOLO = _clean(["방송오프", "방송off", "방송", "방종", "화공"])

def get_base_path():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # 만약 실행 파일이 dist 폴더 안에 있다면 한 단계 상위 폴더(DiscordAutoMute)를 반환
        if os.path.basename(exe_dir).lower() == 'dist':
            return os.path.dirname(exe_dir)
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))

def main():
    # pythonw.exe 또는 no-console 실행 시 출력이 없어지면서 발생하는 오류 방지 및 디버깅을 위한 로그 리디렉션
    base_path = get_base_path()
    log_file_path = os.path.join(base_path, "discord_mute_log.txt")
    
    is_gui = False
    if not sys.stdout or not hasattr(sys.stdout, 'isatty'):
        is_gui = True
    elif not sys.stdout.isatty():
        is_gui = True
    elif sys.executable.endswith("pythonw.exe"):
        is_gui = True

    if is_gui:
        sys.stdout = RollingLog(log_file_path, max_lines=100)
        sys.stderr = sys.stdout

    ensure_single_instance()
    
    print(f"\n=========================================================")
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 음성 인식 백그라운드 프로그램 시작")
    print(f"=========================================================")

    if not is_admin():
        print("---------------------------------------------------------")
        print("[권한 안내] 관리자 권한으로 실행되지 않았습니다.")
        print("전역 단축키(keyboard) 사용 시 관리자 권한이 없으면 게임 중 인식이 안 될 수 있습니다.")
        print("문제가 있다면 런처나 시스템을 관리자 권한으로 설정해 주세요.")
        print("---------------------------------------------------------\n")

    recognizer = sr.Recognizer()
    
    while True:
        # 1. 디스코드 실행 대기
        detected_app = get_running_discord_name()
        if not detected_app:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [대기] Discord / Discord Canary가 실행되기를 기다립니다...")
            while True:
                time.sleep(5)
                detected_app = get_running_discord_name()
                if detected_app:
                    break
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [시작] {detected_app} 프로세스 감지됨!")
            
        # 2. 최적의 실제 마이크 장치 탐색 (게임패드/가상 마이크 자동 배제)
        mic_idx, mic_name = get_best_microphone()
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [마이크 연결] '{mic_name}' (장치번호 {mic_idx}) 선택됨")
        
        try:
            mic_source = sr.Microphone(device_index=mic_idx) if mic_idx is not None else sr.Microphone()
        except Exception as e:
            print(f"[경고] 지정 마이크 열기 실패 ({e}), 기본 마이크로 연결합니다.")
            mic_source = sr.Microphone()

        # 3. 디스코드가 켜지면 마이크 활성화 및 음성 인식 시작
        with mic_source as source:
            print("[안내] 마이크 주변 소음을 조정 중입니다...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            # 잡음으로 인한 UnknownValueError 폭주를 막고 사람 목소리에 명확히 반응하도록 보정
            if recognizer.energy_threshold < 200:
                recognizer.energy_threshold = 200
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.5    # 말이 끝났을 때 0.5초만에 신속하게 인식 완료
            recognizer.phrase_threshold = 0.2   # '마이크' 등 짧은 단어도 놓치지 않고 즉시 포착
            recognizer.non_speaking_duration = 0.3
            print(f"[완료] 현재 민감도(energy_threshold): {recognizer.energy_threshold:.2f}")
            print("[완료] 백그라운드 대기 중 (Discord 음성인식 모드)")
            
            while is_discord_running():
                try:
                    audio = recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    text = recognizer.recognize_google(audio, language="ko-KR")
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 인식 완료: '{text}'")
                    
                    text_clean = text.lower().replace(" ", "")
                    
                    # 1. 연결 끊기 명령어 인식 ("좀이따", "좀있다", "나간다", "연결끊기" 등)
                    is_disconnect_triggered = any(kw in text_clean for kw in [
                        "좀이따", "좀있다", "좀잇다", "이따옴", "좀이따옴", "좀있다옴", "이따가"
                    ])
                    
                    # 2. 마이크 제어 ("마이크", "음소거", "뮤트", "마이클", "mic" 단어만 말해도 즉시 실행)
                    is_mute_triggered = False
                    if not is_disconnect_triggered:
                        is_mute_triggered = any(kw in text_clean for kw in [
                            "마이크", "마이클", "음소거", "뮤트", "마이코프", "마이콘", "mic"
                        ]) or any(direct in text_clean for direct in MIC_OFF_DIRECT) or any(direct in text_clean for direct in MIC_ON_DIRECT)
                        
                        if not is_mute_triggered:
                            for m_kw in MIC_KEYWORDS:
                                for o_kw in OFF_KEYWORDS:
                                    if m_kw in text_clean and o_kw in text_clean:
                                        is_mute_triggered = True
                                        break
                                if is_mute_triggered:
                                    break
                                    
                        if not is_mute_triggered and (text_clean in OFF_SOLO or text_clean in ON_SOLO):
                            is_mute_triggered = True

                    # 3. 방송 종료 명령어 인식 ("방송", "화공", "방종" 등)
                    is_stream_off_triggered = False
                    if not is_disconnect_triggered and not is_mute_triggered:
                        is_stream_off_triggered = any(kw in text_clean for kw in [
                            "방송", "화공", "방종", "화면공유"
                        ]) or any(kw in text_clean for kw in STREAM_OFF_KEYWORDS)
                    
                    if is_disconnect_triggered:
                        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [알림] '좀이따/연결끊기' 인식됨 -> Discord 단축키(Ctrl+Page Up) 전송")
                        send_discord_hotkey('ctrl+page up')
                        time.sleep(0.5)
                    elif is_mute_triggered:
                        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [알림] '마이크' 제어 인식됨 -> Discord 단축키(Ctrl+Page Down) 전송")
                        send_discord_hotkey('ctrl+page down')
                        time.sleep(0.5)
                    elif is_stream_off_triggered:
                        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [알림] '방송/화공' 종료 인식됨 -> Discord 단축키(Alt+Page Up) 전송")
                        send_discord_hotkey('alt+page up')
                        time.sleep(0.5)
                        
                except sr.WaitTimeoutError:
                    pass
                except sr.UnknownValueError:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [오류/UnknownValueError] 음성을 명확히 인식할 수 없습니다.")
                except sr.RequestError as e:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [오류/RequestError] 구글 API 요청 실패: {e}")
                    time.sleep(2)
                except KeyboardInterrupt:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [종료] 사용자 강제 종료")
                    return
                except Exception as e:
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [예기치 않은 오류] {e}")
                    import traceback
                    traceback.print_exc(file=sys.stdout)
                    time.sleep(2)
                    break # 마이크 스트림 오류(Stream closed 등) 발생 시 루프를 탈출하여 마이크를 처음부터 재설정하도록 유도
                    
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [안내] {detected_app}가 종료되어 마이크 사용을 중단하고 대기 모드로 전환합니다.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        base_path = get_base_path()
        with open(os.path.join(base_path, "crash_log.txt"), "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] CRASH: {e}\n")
            import traceback
            traceback.print_exc(file=f)
