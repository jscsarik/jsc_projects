import os
import sys
import time
import json
import threading
import io
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageOps

# 콘솔 출력 시 cp949 인코딩 에러 방지
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import customtkinter as ctk
import pygame
import keyboard
import psutil
import win32gui
import win32process
import win32api

# ====================================================================
# [기본 설정 및 상수]
# ====================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AUDIO_DIR = os.path.join(SCRIPT_DIR, "audio") if os.path.isdir(os.path.join(SCRIPT_DIR, "audio")) else SCRIPT_DIR
TARGET_PROCESS_NAME = "supermegabaseball.exe"  # 감지할 게임 실행 파일명
CONFIG_FILE = os.path.join(SCRIPT_DIR, "lineup.json")  # 타순 저장 파일명

# 애슐리 퀸즈 (ASHLEY QUEENS) 기본 선발 타순 (1번 ~ 9번)
DEFAULT_LINEUP = [
    "백찬하",
    "이정학",
    "김상훈",
    "이유준",
    "김진욱",
    "김범진",
    "정승찬",
    "김민석",
    "이건하"
]

# 기본 포지션 리스트
DEFAULT_POSITIONS = ["LF", "CF", "1B", "DH", "SS", "RF", "C", "3B", "2B"]
AVAILABLE_POSITIONS = ["LF", "CF", "RF", "1B", "2B", "3B", "SS", "C", "DH"]

POSITION_ROLES = {
    "LF": "좌익수",
    "CF": "중견수",
    "RF": "우익수",
    "1B": "1루수",
    "2B": "2루수",
    "3B": "3루수",
    "SS": "유격수",
    "C": "포수",
    "DH": "지명타자",
    "SP": "선발투수",
    "RP": "불펜투수",
    "CP": "마무리투수"
}

# 선발투수 로테이션 명단 (순서: 권영호 -> 이지원 -> 김규태 -> 김병서)
STARTING_ROTATION = ["권영호", "이지원", "김규태", "김병서"]

# 애슐리 퀸즈 22명 선수단 전체 등번호, 1st/2nd 포지션 표기 메타데이터
PLAYER_ROSTER = {
    # 선발 타자 9명
    "백찬하": {"num": 25, "pos": "LF", "pos_full": "LF/CF", "role": "좌익수"},
    "이정학": {"num": 10, "pos": "CF", "pos_full": "CF/RF", "role": "중견수"},
    "김상훈": {"num": 3, "pos": "1B", "pos_full": "1B/C", "role": "1루수"},
    "이유준": {"num": 9, "pos": "DH", "pos_full": "1B/DH", "role": "지명타자"},
    "김진욱": {"num": 15, "pos": "SS", "pos_full": "SS/2B", "role": "유격수"},
    "김범진": {"num": 30, "pos": "RF", "pos_full": "RF/SS", "role": "우익수"},
    "정승찬": {"num": 66, "pos": "C", "pos_full": "C", "role": "포수"},
    "김민석": {"num": 8, "pos": "3B", "pos_full": "3B/LF", "role": "3루수"},
    "이건하": {"num": 19, "pos": "2B", "pos_full": "2B/3B", "role": "2루수"},
    # 벤치 대기 4명 (사용자 요청: 1st/2nd 포지션 표기 e.g. RF/LF, 2B/3B)
    "서석진": {"num": 0, "pos": "2B", "pos_full": "2B/3B", "role": "내야수"},
    "이해원": {"num": 31, "pos": "CF", "pos_full": "CF/RF", "role": "외야수"},
    "홍동기": {"num": 27, "pos": "RF", "pos_full": "RF/LF", "role": "외야수"},
    "오건영": {"num": 61, "pos": "C", "pos_full": "C/IF", "role": "포수"},
    # 선발 투수 4명
    "권영호": {"num": 18, "pos": "SP", "pos_full": "SP", "role": "선발투수"},
    "이지원": {"num": 47, "pos": "SP", "pos_full": "SP", "role": "선발투수"},
    "김규태": {"num": 29, "pos": "SP", "pos_full": "SP", "role": "선발투수"},
    "김병서": {"num": 34, "pos": "SP", "pos_full": "SP", "role": "선발투수"},
    # 불펜 투수 5명
    "이권희": {"num": 24, "pos": "RP", "pos_full": "RP", "role": "불펜투수"},
    "김준겸": {"num": 67, "pos": "RP", "pos_full": "RP", "role": "불펜투수"},
    "오동환": {"num": 33, "pos": "RP", "pos_full": "RP", "role": "불펜투수"},
    "이정용": {"num": 38, "pos": "RP", "pos_full": "RP", "role": "불펜투수"},
    "제임스": {"num": 96, "pos": "CP", "pos_full": "CP", "role": "마무리투수"},
    "이제임스": {"num": 96, "pos": "CP", "pos_full": "CP", "role": "마무리투수"},
}


def get_player_meta(name: str):
    clean = name.strip()
    return PLAYER_ROSTER.get(clean, {"num": "--", "pos": "선수", "pos_full": "선수", "role": "야구선수"})


def extract_id3_album_art(mp3_path: str):
    if not mp3_path or not os.path.isfile(mp3_path):
        return None
    try:
        with open(mp3_path, "rb") as f:
            header = f.read(10)
            if header[:3] != b"ID3":
                return None
            version = header[3]
            size = ((header[6] & 0x7F) << 21) | ((header[7] & 0x7F) << 14) | ((header[8] & 0x7F) << 7) | (header[9] & 0x7F)
            tag_data = f.read(size)
            pos = 0
            while pos < len(tag_data) - 10:
                frame_id = tag_data[pos : pos + 4]
                if frame_id == b"\x00\x00\x00\x00":
                    break
                if version == 4:
                    frame_size = ((tag_data[pos + 4] & 0x7F) << 21) | ((tag_data[pos + 5] & 0x7F) << 14) | ((tag_data[pos + 6] & 0x7F) << 7) | (tag_data[pos + 7] & 0x7F)
                else:
                    frame_size = int.from_bytes(tag_data[pos + 4 : pos + 8], byteorder="big")
                pos += 10
                frame_data = tag_data[pos : pos + frame_size]
                pos += frame_size
                if frame_id == b"APIC":
                    enc = frame_data[0]
                    mime_end = frame_data.find(b"\x00", 1)
                    desc_start = mime_end + 2
                    if enc in (1, 2):
                        desc_end = frame_data.find(b"\x00\x00", desc_start)
                        if desc_end % 2 != desc_start % 2:
                            desc_end = frame_data.find(b"\x00\x00", desc_end + 1)
                        pic_data = frame_data[desc_end + 2 :]
                    else:
                        desc_end = frame_data.find(b"\x00", desc_start)
                        pic_data = frame_data[desc_end + 1 :]
                    return Image.open(io.BytesIO(pic_data))
    except Exception as e:
        print(f"[앨범아트 추출 에러 - {mp3_path}]: {e}")
    return None


def get_pitcher_photo(folder: str, name: str, target_size=(72, 72)) -> Image.Image:
    """선발투수 카드용 사진 (72x72)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    profiles_dir = os.path.join(script_dir, "profiles")
    meta = get_player_meta(name)
    candidates = []
    if meta.get("num") not in (None, "--"):
        candidates.append(os.path.join(profiles_dir, f"{meta['num']}.png"))
    candidates.append(os.path.join(profiles_dir, f"{name}.png"))
    candidates.append(os.path.join(profiles_dir, f"투수_{name}.png"))
    for cand in candidates:
        if os.path.isfile(cand):
            try:
                return Image.open(cand).resize(target_size, Image.Resampling.LANCZOS)
            except Exception:
                pass

    mp3_path = os.path.join(folder, f"투수_{name}_등장곡.mp3")
    pil_img = extract_id3_album_art(mp3_path)

    if pil_img is None:
        for ext in (".jpg", ".png", ".jpeg"):
            candidate = os.path.join(folder, f"투수_{name}{ext}")
            if os.path.isfile(candidate):
                try:
                    pil_img = Image.open(candidate)
                    break
                except Exception:
                    pass

    if pil_img is None:
        pil_img = Image.new("RGB", target_size, color="#230d3d")
        draw = ImageDraw.Draw(pil_img)
        draw.rectangle([0, 0, target_size[0] - 1, target_size[1] - 1], outline="#ffd166", width=2)
        draw.text((10, 24), f"⚾ {name}", fill="#ffffff")

    return pil_img.resize(target_size, Image.Resampling.LANCZOS)


def get_player_spotlight_image(folder: str, name: str, is_pitcher: bool = False, target_size=(240, 320)) -> Image.Image:
    """중앙 전광판 스포트라이트용 3:4 세로 비율 이미지 (240x320)"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    profiles_dir = os.path.join(script_dir, "profiles")
    meta = get_player_meta(name)
    candidates = []
    if meta.get("num") not in (None, "--"):
        candidates.append(os.path.join(profiles_dir, f"{meta['num']}.png"))
    candidates.append(os.path.join(profiles_dir, f"{name}.png"))
    if is_pitcher:
        candidates.append(os.path.join(profiles_dir, f"투수_{name}.png"))
    for cand in candidates:
        if os.path.isfile(cand):
            try:
                img = Image.open(cand)
                return ImageOps.fit(img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
            except Exception:
                pass

    if is_pitcher:
        mp3_path = os.path.join(folder, f"투수_{name}_등장곡.mp3")
    else:
        mp3_path = os.path.join(folder, f"{name}_등장곡.mp3")

    pil_img = extract_id3_album_art(mp3_path)
    if pil_img:
        try:
            return ImageOps.fit(pil_img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
        except Exception:
            return pil_img.resize(target_size, Image.Resampling.LANCZOS)

    # 앨범아트 미등록 시 애슐리 퀸즈 대형 전광판 그래픽 카드 플레이스홀더 (3:4 비율)
    w, h = target_size
    card = Image.new("RGBA", (w, h), color=(24, 10, 42, 255))
    draw = ImageDraw.Draw(card)

    draw.rectangle([0, 0, w - 1, h - 1], outline=(255, 209, 102, 255), width=2)

    logo_path = os.path.join(script_dir, "assets", "team_logo.png")
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_w = int(w * 0.82)
            logo_h = int(logo_w * (logo.height / logo.width))
            if logo_h > h * 0.68:
                logo_h = int(h * 0.68)
                logo_w = int(logo_h * (logo.width / logo.height))
            logo_resized = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            offset_x = (w - logo_w) // 2
            offset_y = 15
            card.paste(logo_resized, (offset_x, offset_y), logo_resized)
        except Exception as e:
            print(f"[로고 로드 실패]: {e}")

    # 카드 하단 골드 테두리 정보 바
    draw.rectangle([8, h - 44, w - 8, h - 8], fill=(45, 18, 77, 255), outline=(255, 209, 102, 200), width=1)

    meta = get_player_meta(name)
    pos_tag = f"#{meta['num']} {meta['pos_full']}"

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 13)
        font_team = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
        font_team = font

    draw.text((14, h - 37), pos_tag, fill=(255, 209, 102, 255), font=font)
    draw.text((w - 58, h - 35), "애슐리", fill=(100, 223, 223, 255), font=font_team)

    return card


def generate_compact_diamond(field_map: dict, active_batter: str = "", active_pitcher: str = "", size=(270, 210)) -> Image.Image:
    """스포트라이트 우측 하단에 배치될 야구장 다이아몬드 수비 그래픽 (270x210)"""
    w, h = size
    img = Image.new("RGBA", (w, h), (18, 8, 32, 255))
    draw = ImageDraw.Draw(img)

    # 골드 테두리
    draw.rectangle([0, 0, w - 1, h - 1], outline=(255, 209, 102, 180), width=1)

    line_col = (243, 156, 18, 255)
    foul_col = (255, 209, 102, 200)

    # 외야 펜스 호
    draw.arc([14, 8, w - 14, h + 14], start=198, end=342, fill=line_col, width=2)

    # 파울 라인
    home_x, home_y = w // 2, h - 34
    draw.line([(home_x, home_y), (22, 65)], fill=foul_col, width=2)
    draw.line([(home_x, home_y), (w - 22, 65)], fill=foul_col, width=2)

    # 내야 흙 경계
    draw.arc([w // 2 - 65, h // 2 - 32, w // 2 + 65, h - 20], start=205, end=335, fill=line_col, width=1)

    # 베이스 계산
    d_size = 38
    b1_x, b1_y = home_x + d_size, home_y - d_size + 3
    b2_x, b2_y = home_x, home_y - 2 * d_size + 7
    b3_x, b3_y = home_x - d_size, home_y - d_size + 3
    mound_x, mound_y = home_x, home_y - d_size + 4

    # 베이스 경로
    draw.line([(home_x, home_y), (b1_x, b1_y), (b2_x, b2_y), (b3_x, b3_y), (home_x, home_y)], fill=line_col, width=2)
    draw.ellipse([mound_x - 10, mound_y - 10, mound_x + 10, mound_y + 10], outline=line_col, width=1)
    draw.ellipse([mound_x - 3, mound_y - 3, mound_x + 3, mound_y + 3], fill=(230, 126, 34, 255))

    def draw_base(cx, cy, r=3):
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=(255, 255, 255, 255))

    draw_base(b1_x, b1_y)
    draw_base(b2_x, b2_y)
    draw_base(b3_x, b3_y)
    draw.polygon([(home_x - 3, home_y - 2), (home_x + 3, home_y - 2), (home_x + 4, home_y + 2), (home_x, home_y + 5), (home_x - 4, home_y + 2)], fill=(255, 255, 255, 255))

    pos_coords = {
        "CF": (home_x, 16),
        "LF": (48, 36),
        "RF": (w - 48, 36),
        "SS": (home_x - 34, b2_y + 4),
        "2B": (home_x + 34, b2_y + 4),
        "3B": (b3_x - 20, b3_y + 2),
        "1B": (b1_x + 20, b1_y + 2),
        "P":  (mound_x, mound_y - 13),
        "C":  (home_x, home_y + 12),
        "DH": (28, h - 14)
    }

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 11)
    except Exception:
        font = ImageFont.load_default()

    for pos, (x, y) in pos_coords.items():
        name = field_map.get(pos, pos)
        is_highlight = (name == active_batter or name == active_pitcher)
        fill_col = (255, 209, 102, 255) if is_highlight else (255, 255, 255, 255)
        bbox = draw.textbbox((0, 0), name, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw // 2 + 1, y - th // 2 + 1), name, fill=(0, 0, 0, 255), font=font)
        draw.text((x - tw // 2, y - th // 2), name, fill=fill_col, font=font)

    return img


# ====================================================================
# [프로세스 및 윈도우 포커스 감지 유틸리티]
# ====================================================================
def is_process_focused(target_process_name: str) -> bool:
    if not target_process_name:
        return True
    
    target = target_process_name.lower().strip()
    if not target.endswith(".exe"):
        target += ".exe"

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return True
        res = win32process.GetWindowThreadProcessId(hwnd)
        if not res or len(res) < 2:
            return True
        pid = res[1]
        if pid <= 0:
            return True

        # 1. 본 응원가 프로그램 창에 포커스가 있는 경우에도 항상 단축키 허용
        if pid == os.getpid():
            return True

        # 2. 지정된 게임 프로세스 검사
        try:
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.name().lower() == target:
                    return True
        except Exception:
            pass

        # 3. 윈도우 타이틀 키워드로도 게임 여부 검사 (권한 제한 또는 전체화면 모드 대비)
        try:
            title = win32gui.GetWindowText(hwnd).lower()
            if "super mega baseball" in title or "smb4" in title or "ashley queens" in title:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return True


def get_game_status_text(target_process_name: str) -> tuple[str, str]:
    target = target_process_name.lower().strip()
    if not target.endswith(".exe"):
        target += ".exe"

    is_running = False
    try:
        for p in psutil.process_iter(['name']):
            try:
                if p.info['name'] and p.info['name'].lower() == target:
                    is_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass

    if not is_running:
        return "게임 미실행", "#95a5a6"
    
    if is_process_focused(target_process_name):
        return "게임 활성화 (포커스됨)", "#2ecc71"
    else:
        return "게임 실행 중 (백그라운드)", "#ffd166"


# ====================================================================
# [방송국급 크로스페이드 오디오 엔진 (Sound & Channel 기반)]
# ====================================================================
class AudioEngine:
    def __init__(self, status_callback=None):
        self.status_callback = status_callback
        self.lock = threading.Lock()
        self.master_volume = 0.8
        self.sound_cache = {}

        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.set_num_channels(8)
            self.channel_a = pygame.mixer.Channel(0)
            self.channel_b = pygame.mixer.Channel(1)
            self.active_channel_is_a = False
            self.set_volume(self.master_volume)
        except Exception as e:
            print(f"[오디오 엔진 초기화 실패]: {e}")

        self.current_sequence_id = 0
        self.current_stop_event = threading.Event()
        self.play_thread = None
        self.is_playing = False

    def get_sound(self, path: str):
        if not path or not os.path.isfile(path):
            return None
        if path not in self.sound_cache:
            try:
                self.sound_cache[path] = pygame.mixer.Sound(path)
            except Exception as e:
                print(f"[사운드 로드 오류 - {path}]: {e}")
                return None
        return self.sound_cache[path]

    def set_volume(self, volume: float):
        self.master_volume = max(0.0, min(1.0, volume))
        try:
            self.channel_a.set_volume(self.master_volume)
            self.channel_b.set_volume(self.master_volume)
        except Exception:
            pass

    def update_status(self, message: str, level: str = "info"):
        if self.status_callback:
            self.status_callback(message, level)

    def stop(self, reason: str = "즉시 정지"):
        with self.lock:
            self.current_sequence_id += 1
            self.current_stop_event.set()
            try:
                self.channel_a.stop()
                self.channel_b.stop()
            except Exception:
                pass
            self.is_playing = False
        self.update_status(f"⏹️ [{reason}] 대기 중", level="stopped")

    def fadeout(self, duration_ms: int = 1500, reason: str = "페이드아웃 정지"):
        with self.lock:
            self.current_sequence_id += 1
            self.current_stop_event.set()
            try:
                self.channel_a.fadeout(duration_ms)
                self.channel_b.fadeout(duration_ms)
            except Exception:
                pass
            self.is_playing = False
        self.update_status(f"🔴 [{reason}] 소리를 줄이며 종료 중...", level="stopped")

    def play_batter_sequence(self, slot_num: int, player_name: str, walkup_file: str, cheer_file: str, crossfade_ms: int = 1000, cheer_only: bool = False):
        with self.lock:
            self.current_sequence_id += 1
            seq_id = self.current_sequence_id
            self.current_stop_event.set()
            self.current_stop_event = threading.Event()
            stop_event = self.current_stop_event

            old_channel = self.channel_a if self.active_channel_is_a else self.channel_b
            new_channel = self.channel_b if self.active_channel_is_a else self.channel_a
            self.active_channel_is_a = not self.active_channel_is_a

            try:
                old_channel.fadeout(crossfade_ms)
            except Exception:
                pass

        self.play_thread = threading.Thread(
            target=self._run_sequence_worker,
            args=(seq_id, stop_event, slot_num, player_name, walkup_file, cheer_file, crossfade_ms, cheer_only, new_channel),
            daemon=True
        )
        self.play_thread.start()

    def _run_sequence_worker(self, seq_id, stop_event, slot_num, player_name, walkup_file, cheer_file, crossfade_ms, cheer_only, channel):
        disp_name = f"{slot_num}번 {player_name}" if slot_num > 0 else player_name

        try:
            self.is_playing = True

            if not cheer_only and walkup_file and os.path.isfile(walkup_file):
                walkup_sound = self.get_sound(walkup_file)
                if walkup_sound is None:
                    self.update_status(f"⚠️ [{disp_name}] 등장곡 로드 실패", level="warning")
                else:
                    self.update_status(f"🎵 [{disp_name}] 등장곡 재생 중... (1.0s 교차전환)", level="walkup")
                    channel.play(walkup_sound, fade_ms=crossfade_ms)

                    while channel.get_busy():
                        if stop_event.is_set() or self.current_sequence_id != seq_id:
                            return
                        time.sleep(0.03)

                    if stop_event.is_set() or self.current_sequence_id != seq_id:
                        return

                    if cheer_file and os.path.isfile(cheer_file):
                        self.update_status(f"⏳ [{disp_name}] 1초 대기 후 응원가 시작...", level="waiting")
                        for _ in range(20):
                            if stop_event.is_set() or self.current_sequence_id != seq_id:
                                return
                            time.sleep(0.05)

            if cheer_file and os.path.isfile(cheer_file):
                cheer_sound = self.get_sound(cheer_file)
                if cheer_sound is None:
                    self.update_status(f"⚠️ [{disp_name}] 응원가 로드 실패", level="warning")
                    return

                if cheer_only:
                    self.update_status(f"🎺 [{disp_name}] 응원가 즉시 재생 중...", level="cheer")
                    channel.play(cheer_sound, fade_ms=crossfade_ms)
                else:
                    self.update_status(f"🎺 [{disp_name}] 응원가 재생 시작!", level="cheer")
                    channel.play(cheer_sound)

                while channel.get_busy():
                    if stop_event.is_set() or self.current_sequence_id != seq_id:
                        return
                    time.sleep(0.03)

                if stop_event.is_set() or self.current_sequence_id != seq_id:
                    return

            self.update_status(f"✅ [{disp_name}] 재생 완료 (대기 중)", level="idle")

        except Exception as e:
            self.update_status(f"❌ 오디오 재생 실패: {e}", level="error")
        finally:
            if self.current_sequence_id == seq_id:
                self.is_playing = False


# ====================================================================
# [메인 GUI: 애슐리 퀸즈 KBO 전광판 플레이어 (CustomTkinter 와이드 1380x880)]
# ====================================================================
class SMB4CheerPlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 전광판 와이드 창 설정 (1380x880)
        self.title("ASHLEY QUEENS - KBO 전광판 응원가 플레이어")
        self.geometry("1380x880")
        self.minsize(1340, 840)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#0e0517")

        # 설정 및 상태 변수
        self.audio_dir_var = tk.StringVar(value=DEFAULT_AUDIO_DIR)
        self.process_name_var = tk.StringVar(value=TARGET_PROCESS_NAME)
        self.focus_check_var = tk.BooleanVar(value=True)

        # 1~9번 슬롯 위젯 참조
        self.slot_frames = []         # 1~9번 슬롯 행 프레임
        self.slot_order_labels = []   # 1~9번 타순 번호 라벨
        self.slot_num_labels = []     # 1~9번 등번호 라벨
        self.slot_pos_menus = []      # 1~9번 포지션 선택 드롭다운
        self.slot_cards = []          # 1~9번 선수 카드 프레임
        self.slot_name_labels = []    # 1~9번 선수 이름 라벨
        self.slot_badges = []         # 1~9번 (등장곡배지, 응원가배지)
        self.slot_players = [""] * 9  # 1~9번 현재 선수 이름 리스트
        self.slot_positions = list(DEFAULT_POSITIONS) # 1~9번 각 타순별 포지션 리스트
        self.current_batter_index = 0 # 현재 타순 인덱스 (1~9, 0은 미지정)

        # 디바운스 타임스탬프
        self.last_next_hotkey_time = 0.0
        self.last_next_cheer_hotkey_time = 0.0
        self.last_pitcher_hotkey_time = 0.0
        self.last_hotkey_time = 0.0

        # 보유 선수 명단
        self.all_available_players = set()
        self.all_available_pitchers = set()
        self.current_pitcher = "권영호"  # 기본 선발투수
        self.starter_widgets = {}

        # 드래그 & 드롭 상태 관리 변수
        self.drag_window = None
        self.dragged_player = None
        self.drag_source_slot = None

        # 현재 전광판 스포트라이트(썸네일) 상태 및 5초 자동 투수 복귀 타이머 ID
        self.current_spotlight_player = "백찬하"
        self.current_spotlight_is_pitcher = False
        self.pitcher_revert_timer_id = None

        # 오디오 엔진 인스턴스
        self.audio_engine = AudioEngine(status_callback=self.on_audio_status_update)

        # UI 위젯 구성
        self._create_ui()

        # 음원 폴더 분석 및 라인업 초기화
        self._refresh_available_players()
        self._load_or_init_lineup()

        # 글로벌 단축키 등록
        self._register_global_hotkeys()

        # 주기적 게임 상태 업데이트 타이머 (1초마다 갱신)
        self._schedule_game_status_check()

        # 윈도우 종료 이벤트 핸들러
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ----------------------------------------------------------------
    # UI 위젯 배치 (전광판 와이드 레이아웃)
    # ----------------------------------------------------------------
    def _create_ui(self):
        # 1. 최상단 전광판 시그니처 헤더 바
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#180a2b", border_width=1, border_color="#ffd166")
        header_frame.pack(fill="x", padx=14, pady=(8, 2))

        # 로고 이미지 로드 및 헤더 타이틀
        header_left = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_left.pack(side="left", padx=12, pady=6)

        logo_path = os.path.join(SCRIPT_DIR, "assets", "team_logo.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path).convert("RGBA").resize((52, 46), Image.Resampling.LANCZOS)
                self.team_logo_ctk = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(52, 46))
                lbl_logo = ctk.CTkLabel(header_left, image=self.team_logo_ctk, text="")
                lbl_logo.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_box = ctk.CTkFrame(header_left, fg_color="transparent")
        title_box.pack(side="left")

        title_label = ctk.CTkLabel(
            title_box,
            text="👑 ASHLEY QUEENS",
            font=ctk.CTkFont(family="Malgun Gothic", size=20, weight="bold"),
            text_color="#ffd166"
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            title_box,
            text="애슐리 퀸즈 KBO 전광판 라이브 응원 플레이어",
            font=ctk.CTkFont(family="Malgun Gothic", size=11),
            text_color="#b8a7d1"
        )
        subtitle_label.pack(anchor="w")

        # 헤더 중앙: 게임 상태 배지
        header_center = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_center.pack(side="left", expand=True)

        self.game_status_badge = ctk.CTkLabel(
            header_center,
            text="🎮 게임 상태 확인 중...",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#ffd166"
        )
        self.game_status_badge.pack(side="left", padx=10)

        # 헤더 우측: 볼륨 조절 슬라이더
        volume_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        volume_frame.pack(side="right", padx=15, pady=6)

        self.volume_label = ctk.CTkLabel(
            volume_frame,
            text="🔊 볼륨: 80%",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#ffd166"
        )
        self.volume_label.pack(side="left", padx=(0, 10))

        self.volume_slider = ctk.CTkSlider(
            volume_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=130,
            button_color="#ffd166",
            button_hover_color="#ffe49e",
            progress_color="#9d4edd",
            command=self._on_volume_change
        )
        self.volume_slider.set(80)
        self.volume_slider.pack(side="left")

        # 헤더 하단 고급스러운 금색 장식 구분선 (Gold Line)
        gold_line_top = ctk.CTkFrame(self, height=2, fg_color="#ffd166")
        gold_line_top.pack(fill="x", padx=14, pady=(2, 6))

        # -------------------------------------------------------------
        # 2. 메인 전광판 바디 (좌: 라인업(435px) / 중: 스코어보드+다이아몬드 / 우: 선발 로테이션(185px))
        # -------------------------------------------------------------
        body_container = ctk.CTkFrame(self, fg_color="transparent")
        body_container.pack(fill="both", expand=True, padx=14, pady=2)

        # [좌측 열: 선발 라인업 1번 ~ 9번]
        lineup_outer = ctk.CTkFrame(body_container, width=435, corner_radius=10, fg_color="#180a2b", border_width=1, border_color="#ffd166")
        lineup_outer.pack(side="left", fill="y", padx=(0, 6), pady=2)
        lineup_outer.pack_propagate(False)

        lineup_header = ctk.CTkFrame(lineup_outer, fg_color="transparent")
        lineup_header.pack(fill="x", padx=10, pady=(8, 4))

        lineup_title = ctk.CTkLabel(
            lineup_header,
            text="📋 선발 라인업 (1~9번 타순)",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            text_color="#ffd166"
        )
        lineup_title.pack(side="left")

        lineup_tip = ctk.CTkLabel(
            lineup_header,
            text="※ 드래그: 타순교체 | 포지션 변경가능",
            font=ctk.CTkFont(family="Malgun Gothic", size=10),
            text_color="#9d8bb7"
        )
        lineup_tip.pack(side="right")

        # 1~9번 슬롯 생성 (빈틈없이 세로 전체를 꽉 채우도록 uniform grid 9분할 적용)
        slots_container = ctk.CTkFrame(lineup_outer, fg_color="transparent")
        slots_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        for r in range(9):
            slots_container.grid_rowconfigure(r, weight=1, uniform="lineup_slot")
        slots_container.grid_columnconfigure(0, weight=1)

        for i in range(1, 10):
            row_frame = ctk.CTkFrame(
                slots_container,
                corner_radius=6,
                fg_color="#24103d" if i % 2 == 1 else "#1e0c33",
                border_width=1,
                border_color="#3c1864"
            )
            row_frame.grid(row=i - 1, column=0, sticky="nsew", padx=1, pady=2)

            order_badge = ctk.CTkLabel(
                row_frame,
                text=f"{i}번 [Alt+{i}]",
                font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
                width=70,
                anchor="w",
                text_color="#ffffff"
            )
            order_badge.pack(side="left", padx=(6, 2))

            num_badge = ctk.CTkLabel(
                row_frame,
                text="#--",
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                width=32,
                height=22,
                corner_radius=4,
                fg_color="#3b1564",
                text_color="#ffd166"
            )
            num_badge.pack(side="left", padx=2)

            init_pos = DEFAULT_POSITIONS[i - 1] if i - 1 < len(DEFAULT_POSITIONS) else "DH"
            pos_menu = ctk.CTkOptionMenu(
                row_frame,
                values=AVAILABLE_POSITIONS,
                width=52,
                height=22,
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                fg_color="#182744",
                button_color="#2b3a58",
                button_hover_color="#3d4f72",
                dropdown_fg_color="#182744",
                dropdown_hover_color="#2b3a58",
                dropdown_text_color="#64dfdf",
                text_color="#64dfdf",
                command=lambda val, idx=i: self._on_slot_position_changed(idx, val)
            )
            pos_menu.set(init_pos)
            pos_menu.pack(side="left", padx=2)

            card = ctk.CTkFrame(
                row_frame,
                width=90,
                height=26,
                corner_radius=4,
                fg_color="#140722",
                border_width=1,
                border_color="#9d4edd",
                cursor="hand2"
            )
            card.pack(side="left", padx=3)
            card.pack_propagate(False)

            name_lbl = ctk.CTkLabel(
                card,
                text="선택 대기",
                font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
                text_color="#ffffff",
                cursor="hand2"
            )
            name_lbl.pack(expand=True)

            for w in (card, name_lbl):
                w.bind("<ButtonPress-1>", lambda e, idx=i: self._start_drag_from_slot(idx, e))
                w.bind("<B1-Motion>", self._on_drag_motion)
                w.bind("<ButtonRelease-1>", self._on_drag_release)

            swap_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            swap_frame.pack(side="left", padx=2)

            up_btn = ctk.CTkButton(
                swap_frame,
                text="▲",
                width=22,
                height=22,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#3c1864" if i != 1 else "#230f3a",
                hover_color="#7b2cbf" if i != 1 else "#230f3a",
                state="disabled" if i == 1 else "normal",
                command=lambda idx=i: self.swap_slots(idx, idx - 1)
            )
            up_btn.pack(side="left", padx=1)

            down_btn = ctk.CTkButton(
                swap_frame,
                text="▼",
                width=22,
                height=22,
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#3c1864" if i != 9 else "#230f3a",
                hover_color="#7b2cbf" if i != 9 else "#230f3a",
                state="disabled" if i == 9 else "normal",
                command=lambda idx=i: self.swap_slots(idx, idx + 1)
            )
            down_btn.pack(side="left", padx=1)

            walkup_badge = ctk.CTkLabel(
                row_frame,
                text="등장 ✗",
                font=ctk.CTkFont(family="Malgun Gothic", size=9, weight="bold"),
                width=44,
                height=20,
                corner_radius=4,
                fg_color="#301548",
                text_color="#95a5a6"
            )
            walkup_badge.pack(side="left", padx=2)

            cheer_badge = ctk.CTkLabel(
                row_frame,
                text="응원 ✗",
                font=ctk.CTkFont(family="Malgun Gothic", size=9, weight="bold"),
                width=44,
                height=20,
                corner_radius=4,
                fg_color="#301548",
                text_color="#95a5a6"
            )
            cheer_badge.pack(side="left", padx=2)

            play_btn = ctk.CTkButton(
                row_frame,
                text="▶",
                width=26,
                height=22,
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                fg_color="#5a189a",
                hover_color="#7b2cbf",
                command=lambda idx=i: self.trigger_slot(idx)
            )
            play_btn.pack(side="right", padx=(2, 4))

            self.slot_frames.append(row_frame)
            self.slot_order_labels.append(order_badge)
            self.slot_num_labels.append(num_badge)
            self.slot_pos_menus.append(pos_menu)
            self.slot_cards.append(card)
            self.slot_name_labels.append(name_lbl)
            self.slot_badges.append((walkup_badge, cheer_badge))

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # [중앙 열: 대형 스포트라이트 (2비율) + 하단 다이아몬드/컨트롤 (1비율)]
        # -------------------------------------------------------------
        center_outer = ctk.CTkFrame(body_container, corner_radius=10, fg_color="#180a2b", border_width=1, border_color="#ffd166")
        center_outer.pack(side="left", fill="both", expand=True, padx=4, pady=2)

        # 하단 영역: NEXT 타순 및 재생 버튼 바 (height=115px 고정 밀착, 전체 가로폭 활용)
        lower_content = ctk.CTkFrame(center_outer, height=115, fg_color="transparent")
        lower_content.pack(side="bottom", fill="x", padx=10, pady=(2, 8))
        lower_content.pack_propagate(False)

        # NEXT 타순 예고 바 (전체 가로폭 시원하게 활용)
        next_frame = ctk.CTkFrame(lower_content, height=36, corner_radius=8, fg_color="#1a0a2f", border_width=1, border_color="#ffd166")
        next_frame.pack(fill="x", pady=(2, 6))

        next_hdr = ctk.CTkFrame(next_frame, fg_color="transparent")
        next_hdr.pack(side="left", padx=(12, 6), pady=6)

        next_title = ctk.CTkLabel(
            next_hdr,
            text=">> NEXT 타순 :",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#ffd166"
        )
        next_title.pack(side="left")

        self.next_batters_container = ctk.CTkFrame(next_frame, fg_color="transparent")
        self.next_batters_container.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=4)

        self.next_batter_labels = []
        for n_i in range(3):
            pill = ctk.CTkLabel(
                self.next_batters_container,
                text=f"{n_i + 2}번 선수 대기",
                font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
                fg_color="#2b124a",
                text_color="#ffffff",
                corner_radius=6,
                height=26,
                padx=12
            )
            pill.pack(side="left", padx=4, expand=True, fill="x")
            self.next_batter_labels.append(pill)

        # 시원하게 확장된 [다음 타자] & [응원가만] 메인 재생 버튼 바 (height 44px)
        buttons_row = ctk.CTkFrame(lower_content, fg_color="transparent")
        buttons_row.pack(fill="x", pady=(0, 2))

        self.next_button = ctk.CTkButton(
            buttons_row,
            text="⏭️ 다음 타자 자동재생 (Alt + `)",
            command=self.play_next_batter,
            fg_color="#7209b7",
            hover_color="#9d4edd",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            height=44
        )
        self.next_button.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.next_cheer_button = ctk.CTkButton(
            buttons_row,
            text="🎺 응원가만 즉시재생 (Shift + `)",
            command=lambda: self.play_next_batter(cheer_only=True),
            fg_color="#e85d04",
            hover_color="#f48c06",
            font=ctk.CTkFont(family="Malgun Gothic", size=13, weight="bold"),
            height=44
        )
        self.next_cheer_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # 중앙 상단: 스포트라이트 전광판 박스 (fill="both", expand=True로 웅장하게 차지)
        self.spotlight_box = ctk.CTkFrame(center_outer, corner_radius=8, fg_color="#1f0d36", border_width=2, border_color="#ffd166")
        self.spotlight_box.pack(side="top", fill="both", expand=True, padx=10, pady=(8, 4))

        # 전광판 헤더
        spotlight_hdr = ctk.CTkFrame(self.spotlight_box, fg_color="#2b124a", corner_radius=6)
        spotlight_hdr.pack(fill="x", padx=6, pady=(6, 2))

        self.spotlight_tag = ctk.CTkLabel(
            spotlight_hdr,
            text="👑 ASHLEY QUEENS  |  ★ NOW ON PLAY - 현재 타석 / 등판 ★",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#ffd166"
        )
        self.spotlight_tag.pack(pady=4)

        # 상단 콘텐츠: 좌측(3:4 대형 사진 + 포지션 배지 + 아웃/음원정보) + 우측(이름 & 상태 + 야구장 다이아몬드)
        upper_content = ctk.CTkFrame(self.spotlight_box, fg_color="transparent")
        upper_content.pack(fill="both", expand=True, padx=12, pady=(4, 6))

        # 1) 좌측 컬럼: [3:4 비율 세로 사진 (240x320) + 포지션 정보 배지 + 아웃버튼/음원정보]
        photo_column = ctk.CTkFrame(upper_content, width=255, fg_color="transparent")
        photo_column.pack(side="left", fill="y", padx=(0, 16))
        photo_column.pack_propagate(False)

        self.spotlight_photo_frame = ctk.CTkFrame(photo_column, width=245, height=325, corner_radius=8, fg_color="#140722", border_width=1, border_color="#ffd166")
        self.spotlight_photo_frame.pack(side="top")
        self.spotlight_photo_frame.pack_propagate(False)

        default_spotlight_img = get_player_spotlight_image(self.audio_dir_var.get(), "백찬하", is_pitcher=False, target_size=(240, 320))
        self.spotlight_ctk_img = ctk.CTkImage(light_image=default_spotlight_img, dark_image=default_spotlight_img, size=(240, 320))
        self.spotlight_photo_lbl = ctk.CTkLabel(self.spotlight_photo_frame, image=self.spotlight_ctk_img, text="")
        self.spotlight_photo_lbl.pack(expand=True)

        # 사진 바로 아래: [포지션 내용 왼쪽 배치 (사용자 요청 반영)]
        self.lbl_spotlight_info = ctk.CTkLabel(
            photo_column,
            text="#25  |  좌익수 (LF/CF)  |  1번 타자",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            text_color="#ffd166",
            fg_color="#24103d",
            corner_radius=5,
            height=26
        )
        self.lbl_spotlight_info.pack(fill="x", pady=(4, 3))

        # 사진 칸 아래 조작 바: [🎵 등장곡 틀기] + [🔴 아웃 (Alt + 0)]
        photo_btn_row = ctk.CTkFrame(photo_column, fg_color="transparent")
        photo_btn_row.pack(fill="x", pady=(2, 2))

        self.spotlight_walkup_button = ctk.CTkButton(
            photo_btn_row,
            text="🎵 등장곡 틀기",
            command=self.play_spotlight_walkup,
            fg_color="#7b2cbf",
            hover_color="#9d4edd",
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            height=26,
            width=116
        )
        self.spotlight_walkup_button.pack(side="left", padx=(0, 4), expand=True, fill="x")

        self.out_button = ctk.CTkButton(
            photo_btn_row,
            text="🔴 아웃 (Alt+0)",
            command=self.fadeout_playback,
            fg_color="#d90429",
            hover_color="#ef233c",
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            height=26,
            width=100
        )
        self.out_button.pack(side="left", expand=True, fill="x")

        # 맨 하단 음원 파일 정보 라벨
        self.lbl_spotlight_track = ctk.CTkLabel(
            photo_column,
            text="📁 백찬하_등장곡 / 응원가.mp3",
            font=ctk.CTkFont(family="Malgun Gothic", size=9),
            text_color="#b8a7d1",
            anchor="w"
        )
        self.lbl_spotlight_track.pack(fill="x", pady=(1, 2))

        # 2) 우측 컬럼: [상단: 초대형 이름 52pt & 상태 배너] + [하단: 야구장 다이아몬드 (3번째 사진 위치)]
        info_panel = ctk.CTkFrame(upper_content, fg_color="transparent")
        info_panel.pack(side="left", fill="both", expand=True, pady=2)

        lbl_team_brand = ctk.CTkLabel(
            info_panel,
            text="👑 애슐리 퀸즈 (ASHLEY QUEENS)",
            font=ctk.CTkFont(family="Malgun Gothic", size=14, weight="bold"),
            text_color="#c77dff"
        )
        lbl_team_brand.pack(anchor="w", pady=(2, 0))

        # 초대형 52pt 볼드 이름
        self.lbl_spotlight_name = ctk.CTkLabel(
            info_panel,
            text="백찬하",
            font=ctk.CTkFont(family="Malgun Gothic", size=52, weight="bold"),
            text_color="#ffffff"
        )
        self.lbl_spotlight_name.pack(anchor="w", pady=(0, 2))

        # 오디오 진행 상태 배너
        status_banner = ctk.CTkFrame(info_panel, corner_radius=6, fg_color="#140722", border_width=1, border_color="#ffd166")
        status_banner.pack(fill="x", pady=(2, 6))

        self.status_icon_label = ctk.CTkLabel(
            status_banner,
            text="🎵 대기 중 - 경기 시작을 기다리는 중입니다",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#06d6a0"
        )
        self.status_icon_label.pack(side="left", padx=12, pady=6)

        # 3번째 사진 위치: [상태 배너 바로 아래에 배치되는 야구장 다이아몬드 수비 그래픽 (270x210)]
        diamond_frame = ctk.CTkFrame(info_panel, corner_radius=8, fg_color="#140722", border_width=1, border_color="#ffd166")
        diamond_frame.pack(fill="both", expand=True, pady=(2, 0))

        init_diamond = generate_compact_diamond({}, active_batter="백찬하", active_pitcher="권영호", size=(270, 210))
        self.diamond_ctk_img = ctk.CTkImage(light_image=init_diamond, dark_image=init_diamond, size=(270, 210))
        self.diamond_lbl = ctk.CTkLabel(diamond_frame, image=self.diamond_ctk_img, text="")
        self.diamond_lbl.pack(expand=True)

        # -------------------------------------------------------------
        # [우측 열: 선발 로테이션 (권영호-이지원-김규태-김병서) - 균등 분할로 짤림/여백 완벽 해결]
        # -------------------------------------------------------------
        pitcher_panel = ctk.CTkFrame(body_container, width=185, corner_radius=10, fg_color="#180a2b", border_width=1, border_color="#ffd166")
        pitcher_panel.pack(side="right", fill="y", padx=(6, 0), pady=2)
        pitcher_panel.pack_propagate(False)

        pitcher_header = ctk.CTkFrame(pitcher_panel, fg_color="transparent")
        pitcher_header.pack(fill="x", padx=6, pady=(6, 2))

        pitcher_title = ctk.CTkLabel(
            pitcher_header,
            text="⚾ 선발 로테이션",
            font=ctk.CTkFont(family="Malgun Gothic", size=12, weight="bold"),
            text_color="#ffd166"
        )
        pitcher_title.pack(anchor="center")

        pitcher_tip = ctk.CTkLabel(
            pitcher_header,
            text="원클릭 등판 (Alt+P)",
            font=ctk.CTkFont(family="Malgun Gothic", size=9),
            text_color="#9d8bb7"
        )
        pitcher_tip.pack(anchor="center")

        folder = self.audio_dir_var.get().strip()
        self.starter_widgets.clear()

        # uniform grid 행 설정으로 4개 선발투수 카드가 동일한 높이(각 130px)로 패널을 완벽하게 채움
        cards_container = ctk.CTkFrame(pitcher_panel, fg_color="transparent")
        cards_container.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        for r in range(4):
            cards_container.grid_rowconfigure(r, weight=1, uniform="pitcher_card")
        cards_container.grid_columnconfigure(0, weight=1)

        for idx, name in enumerate(STARTING_ROTATION):
            meta = get_player_meta(name)
            pil_img = get_pitcher_photo(folder, name, target_size=(72, 72))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(72, 72))

            card = ctk.CTkFrame(
                cards_container,
                corner_radius=6,
                fg_color="#1f0d36",
                border_width=1,
                border_color="#3c1864",
                cursor="hand2"
            )
            card.grid(row=idx, column=0, sticky="nsew", padx=2, pady=3)

            photo_lbl = ctk.CTkLabel(card, image=ctk_img, text="", cursor="hand2")
            photo_lbl.pack(pady=(4, 2))

            lbl_name = ctk.CTkLabel(
                card,
                text=f"{idx + 1}선발 {name} #{meta['num']}",
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                text_color="#ffffff",
                cursor="hand2"
            )
            lbl_name.pack(pady=(0, 2))

            lbl_tag = ctk.CTkLabel(
                card,
                text="[▶ 등판]",
                font=ctk.CTkFont(family="Malgun Gothic", size=9, weight="bold"),
                text_color="#ffd166",
                cursor="hand2"
            )
            lbl_tag.pack(pady=(0, 4))

            def make_hover(c=card, p_name=name):
                def on_enter(e):
                    if p_name != self.current_pitcher:
                        c.configure(fg_color="#2c144d", border_color="#ffd166")
                def on_leave(e):
                    if p_name != self.current_pitcher:
                        c.configure(fg_color="#1f0d36", border_color="#3c1864")
                return on_enter, on_leave

            h_enter, h_leave = make_hover(card, name)
            for w in (card, photo_lbl, lbl_name, lbl_tag):
                w.bind("<Enter>", h_enter)
                w.bind("<Leave>", h_leave)
                w.bind("<ButtonPress-1>", lambda e, p=name: self.trigger_pitcher(p))

            self.starter_widgets[name] = {
                "card": card,
                "photo_lbl": photo_lbl,
                "name_lbl": lbl_name,
                "tag_lbl": lbl_tag,
                "ctk_img": ctk_img
            }

        # -------------------------------------------------------------
        # 3. 하단 고정 영역: 보유 선수 대기석 (1st/2nd 포지션 표기) & 설정 바
        # -------------------------------------------------------------
        bottom_container = ctk.CTkFrame(self, corner_radius=10, fg_color="#180a2b", border_width=1, border_color="#ffd166")
        bottom_container.pack(fill="x", padx=14, pady=(2, 6))

        gold_line_bottom = ctk.CTkFrame(bottom_container, height=2, fg_color="#ffd166")
        gold_line_bottom.pack(fill="x", padx=10, pady=(2, 4))

        bench_header = ctk.CTkFrame(bottom_container, fg_color="transparent")
        bench_header.pack(fill="x", padx=14, pady=(2, 2))

        self.bench_tab_selector = ctk.CTkSegmentedButton(
            bench_header,
            values=["⚾ 타자 대기석 (4명)", "🔥 불펜 투수진 (5명)"],
            command=self._on_bench_tab_change,
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            selected_color="#7b2cbf",
            selected_hover_color="#9d4edd",
            height=26
        )
        self.bench_tab_selector.set("⚾ 타자 대기석 (4명)")
        self.bench_tab_selector.pack(side="left")

        self.bench_tip = ctk.CTkLabel(
            bench_header,
            text="※ 녹색 태그: 선발 출전 중 | 주황 태그: 벤치 대기 | 더블클릭 시 빈자리 자동 배치",
            font=ctk.CTkFont(family="Malgun Gothic", size=10),
            text_color="#9d8bb7"
        )
        self.bench_tip.pack(side="right")

        self.bench_cards_frame = ctk.CTkFrame(bottom_container, fg_color="transparent")
        self.bench_cards_frame.pack(fill="x", padx=12, pady=(2, 4))

        settings_bar = ctk.CTkFrame(bottom_container, fg_color="#120520", corner_radius=6)
        settings_bar.pack(fill="x", padx=10, pady=(2, 6))

        dir_label = ctk.CTkLabel(settings_bar, text="📁 음원 폴더:", font=ctk.CTkFont(family="Malgun Gothic", size=11), text_color="#ffd166")
        dir_label.pack(side="left", padx=(8, 2))

        self.dir_entry = ctk.CTkEntry(settings_bar, textvariable=self.audio_dir_var, font=ctk.CTkFont(family="Malgun Gothic", size=10), height=24)
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=4)

        browse_btn = ctk.CTkButton(settings_bar, text="폴더 변경", width=65, height=24, font=ctk.CTkFont(family="Malgun Gothic", size=10), command=self._browse_audio_dir)
        browse_btn.pack(side="left", padx=2)

        self.focus_checkbox = ctk.CTkCheckBox(
            settings_bar,
            text="SMB4 활성화 시 단축키 동작",
            variable=self.focus_check_var,
            font=ctk.CTkFont(family="Malgun Gothic", size=11),
            text_color="#ffffff",
            checkmark_color="#ffd166"
        )
        self.focus_checkbox.pack(side="left", padx=(10, 6))

        save_lineup_btn = ctk.CTkButton(
            settings_bar,
            text="💾 라인업 저장",
            width=85,
            height=24,
            fg_color="#2a9d8f",
            hover_color="#2ec4b6",
            font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
            command=self.save_lineup
        )
        save_lineup_btn.pack(side="right", padx=(4, 8))

    # ----------------------------------------------------------------
    # 포지션 변경 이벤트
    # ----------------------------------------------------------------
    def _on_slot_position_changed(self, slot_idx: int, new_pos: str):
        self.slot_positions[slot_idx - 1] = new_pos
        self._update_baseball_field()
        if slot_idx == self.current_batter_index:
            player_name = self.slot_players[slot_idx - 1]
            if player_name:
                self._update_scoreboard_spotlight(player_name, is_pitcher=False)
        self.save_lineup(silent=True)

    # ----------------------------------------------------------------
    # 야구장 다이아몬드 수비 포지션 그래픽 갱신 (스포트라이트 우측 하단 270x210)
    # ----------------------------------------------------------------
    def _update_baseball_field(self):
        field_map = {}
        for i in range(9):
            player = self.slot_players[i]
            pos = self.slot_positions[i]
            if player and pos:
                field_map[pos] = player
        if self.current_pitcher:
            field_map["P"] = self.current_pitcher

        # 이미 배치된 선수 집합 (중복 포지션 노출 방지)
        assigned_players = set(p for p in field_map.values() if p)

        all_positions = ["LF", "CF", "RF", "1B", "2B", "3B", "SS", "C", "DH"]
        for pos in all_positions:
            if pos not in field_map or not field_map[pos]:
                for p in self.slot_players:
                    if p and p in PLAYER_ROSTER and PLAYER_ROSTER[p]["pos"] == pos and p not in assigned_players:
                        field_map[pos] = p
                        assigned_players.add(p)
                        break
                if pos not in field_map or not field_map[pos]:
                    for p in DEFAULT_LINEUP:
                        if p in PLAYER_ROSTER and PLAYER_ROSTER[p]["pos"] == pos and p not in assigned_players:
                            field_map[pos] = p
                            assigned_players.add(p)
                            break

        active_batter = self.slot_players[self.current_batter_index - 1] if self.current_batter_index > 0 else ""
        active_pitcher = self.current_pitcher

        pil_field = generate_compact_diamond(field_map, active_batter=active_batter, active_pitcher=active_pitcher, size=(270, 210))
        self.diamond_ctk_img = ctk.CTkImage(light_image=pil_field, dark_image=pil_field, size=(270, 210))
        self.diamond_lbl.configure(image=self.diamond_ctk_img)

    # ----------------------------------------------------------------
    # 드래그 & 드롭 (Drag and Drop) 핵심 로직
    # ----------------------------------------------------------------
    def _create_drag_ghost(self, player_name: str, x: int, y: int):
        if self.drag_window:
            try:
                self.drag_window.destroy()
            except Exception:
                pass

        self.drag_window = tk.Toplevel(self)
        self.drag_window.overrideredirect(True)
        self.drag_window.attributes("-topmost", True)
        self.drag_window.config(bg="#0e0517")

        frame = ctk.CTkFrame(
            self.drag_window,
            corner_radius=6,
            fg_color="#7b2cbf",
            border_width=2,
            border_color="#ffd166"
        )
        frame.pack(padx=2, pady=2)

        meta = get_player_meta(player_name)
        lbl = ctk.CTkLabel(
            frame,
            text=f"⚾ #{meta['num']} {player_name} ({meta['pos_full']})",
            font=ctk.CTkFont(family="Malgun Gothic", size=11, weight="bold"),
            text_color="#ffffff"
        )
        lbl.pack(padx=8, pady=4)
        self.drag_window.geometry(f"+{x + 12}+{y + 12}")

    def _start_drag_from_bench(self, player_name: str, event):
        self.dragged_player = player_name
        self.drag_source_slot = None
        self._create_drag_ghost(player_name, event.x_root, event.y_root)

    def _start_drag_from_slot(self, slot_idx: int, event):
        player_name = self.slot_players[slot_idx - 1]
        if not player_name:
            return
        self.dragged_player = player_name
        self.drag_source_slot = slot_idx
        self._create_drag_ghost(player_name, event.x_root, event.y_root)

    def _get_slot_under_cursor(self, x_root: int, y_root: int) -> int | None:
        for i, frame in enumerate(self.slot_frames):
            try:
                rx = frame.winfo_rootx()
                ry = frame.winfo_rooty()
                rw = frame.winfo_width()
                rh = frame.winfo_height()
                if rx <= x_root <= rx + rw and ry <= y_root <= ry + rh:
                    return i + 1
            except Exception:
                pass
        return None

    def _on_drag_motion(self, event):
        if self.drag_window:
            self.drag_window.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            target_slot = self._get_slot_under_cursor(event.x_root, event.y_root)
            for i, frame in enumerate(self.slot_frames):
                slot_num = i + 1
                if target_slot == slot_num:
                    frame.configure(border_color="#ffd166", border_width=2)
                elif slot_num == self.current_batter_index:
                    frame.configure(border_color="#ffd166", border_width=2)
                else:
                    frame.configure(border_color="#3c1864", border_width=1)

    def _on_drag_release(self, event):
        if self.drag_window:
            try:
                self.drag_window.destroy()
            except Exception:
                pass
            self.drag_window = None

        target_slot = self._get_slot_under_cursor(event.x_root, event.y_root)
        if target_slot and self.dragged_player:
            if self.drag_source_slot:
                self.swap_slots(self.drag_source_slot, target_slot)
            else:
                self.assign_player_to_slot(target_slot, self.dragged_player)

        self._update_current_batter_ui()
        self.dragged_player = None
        self.drag_source_slot = None

    def assign_player_to_slot(self, target_slot: int, player_name: str):
        if player_name in self.slot_players:
            old_idx = self.slot_players.index(player_name) + 1
            if old_idx != target_slot:
                self.swap_slots(old_idx, target_slot)
                return

        prev_player = self.slot_players[target_slot - 1]
        self._set_slot_player(target_slot, player_name)
        self._update_slot_indicator(target_slot)
        self._render_current_bench_tab()
        self._update_next_batters_display()
        self._update_baseball_field()
        self.save_lineup(silent=True)
        self.on_audio_status_update(f"⚾ {target_slot}번 타자에 [{player_name}] 배치 완료", level="info")

    def swap_slots(self, idx1: int, idx2: int):
        if not (1 <= idx1 <= 9 and 1 <= idx2 <= 9) or idx1 == idx2:
            return

        name1 = self.slot_players[idx1 - 1]
        name2 = self.slot_players[idx2 - 1]
        pos1 = self.slot_positions[idx1 - 1]
        pos2 = self.slot_positions[idx2 - 1]

        self._set_slot_player(idx1, name2)
        self._set_slot_player(idx2, name1)

        self.slot_pos_menus[idx1 - 1].set(pos2)
        self.slot_pos_menus[idx2 - 1].set(pos1)
        self.slot_positions[idx1 - 1] = pos2
        self.slot_positions[idx2 - 1] = pos1

        self._update_slot_indicator(idx1)
        self._update_slot_indicator(idx2)

        self._render_current_bench_tab()
        self._update_next_batters_display()
        self._update_baseball_field()
        self.save_lineup(silent=True)

    def _set_slot_player(self, slot_idx: int, player_name: str):
        self.slot_players[slot_idx - 1] = player_name
        lbl = self.slot_name_labels[slot_idx - 1]
        num_lbl = self.slot_num_labels[slot_idx - 1]

        if player_name:
            meta = get_player_meta(player_name)
            lbl.configure(text=player_name, text_color="#ffffff")
            num_lbl.configure(text=f"#{meta['num']}")
        else:
            lbl.configure(text="선택 대기", text_color="#7f8c8d")
            num_lbl.configure(text="#--")

    # ----------------------------------------------------------------
    # 하단 대기석 렌더링 (1st/2nd 포지션 표기 e.g. #27 홍동기 (RF/LF))
    # ----------------------------------------------------------------
    def _on_bench_tab_change(self, selected_tab: str):
        self._render_current_bench_tab()

    def _render_current_bench_tab(self):
        for widget in self.bench_cards_frame.winfo_children():
            widget.destroy()

        tab = self.bench_tab_selector.get()
        if "타자" in tab:
            self.bench_tip.configure(text="※ 녹색 태그: 선발 출전 중 | 주황 태그: 벤치 대기 | 더블클릭 시 빈자리 자동 배치")
            self._render_bench_batters()
        else:
            self.bench_tip.configure(text="※ 투수 카드를 클릭하면 즉시 마운드 등판곡 재생 (Alt+P) | [Alt + 0]으로 강판/종료")
            self._render_bench_pitchers()

    def _render_bench_batters(self):
        sorted_players = sorted(list(self.all_available_players))
        if not sorted_players:
            return

        cols = 6
        for idx, name in enumerate(sorted_players):
            row = idx // cols
            col = idx % cols

            in_lineup = name in self.slot_players
            slot_num = (self.slot_players.index(name) + 1) if in_lineup else None

            card_bg = "#3b1564" if in_lineup else "#1c0b2f"
            border_col = "#ffd166" if in_lineup else "#3c1864"
            tag_text = f" {slot_num}번" if in_lineup else " 대기"
            tag_col = "#06d6a0" if in_lineup else "#ffd166"

            card = ctk.CTkFrame(
                self.bench_cards_frame,
                corner_radius=4,
                fg_color=card_bg,
                border_width=1,
                border_color=border_col,
                cursor="hand2",
                height=30
            )
            card.grid(row=row, column=col, padx=3, pady=2, sticky="nsew")
            card.grid_propagate(False)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(expand=True)

            meta = get_player_meta(name)
            lbl_name = ctk.CTkLabel(
                inner,
                text=f"#{meta['num']} {name} ({meta['pos_full']})",
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                text_color="#ffffff",
                cursor="hand2"
            )
            lbl_name.pack(side="left", padx=2)

            lbl_tag = ctk.CTkLabel(
                inner,
                text=tag_text,
                font=ctk.CTkFont(family="Malgun Gothic", size=9, weight="bold"),
                text_color=tag_col,
                cursor="hand2"
            )
            lbl_tag.pack(side="left", padx=2)

            for w in (card, inner, lbl_name, lbl_tag):
                w.bind("<ButtonPress-1>", lambda e, p=name: self._start_drag_from_bench(p, e))
                w.bind("<B1-Motion>", self._on_drag_motion)
                w.bind("<ButtonRelease-1>", self._on_drag_release)
                w.bind("<Double-Button-1>", lambda e, p=name: self._on_bench_double_click(p))

        for c in range(cols):
            self.bench_cards_frame.grid_columnconfigure(c, weight=1)

    def _render_bench_pitchers(self):
        sorted_pitchers = sorted(list(self.all_available_pitchers))
        if not sorted_pitchers:
            return

        cols = 5
        for idx, name in enumerate(sorted_pitchers):
            row = idx // cols
            col = idx % cols

            is_active = (name == self.current_pitcher)
            card_bg = "#7209b7" if is_active else "#1c0b2f"
            border_col = "#ffd166" if is_active else "#3c1864"
            tag_text = "🔥 등판 중" if is_active else "불펜 대기"
            tag_col = "#ffd166" if is_active else "#64dfdf"

            card = ctk.CTkFrame(
                self.bench_cards_frame,
                corner_radius=4,
                fg_color=card_bg,
                border_width=2 if is_active else 1,
                border_color=border_col,
                cursor="hand2",
                height=30
            )
            card.grid(row=row, column=col, padx=3, pady=2, sticky="nsew")
            card.grid_propagate(False)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(expand=True)

            meta = get_player_meta(name)
            lbl_name = ctk.CTkLabel(
                inner,
                text=f"⚾ #{meta['num']} {name} ({meta['pos_full']})",
                font=ctk.CTkFont(family="Malgun Gothic", size=10, weight="bold"),
                text_color="#ffffff",
                cursor="hand2"
            )
            lbl_name.pack(side="left", padx=2)

            lbl_tag = ctk.CTkLabel(
                inner,
                text=tag_text,
                font=ctk.CTkFont(family="Malgun Gothic", size=9, weight="bold"),
                text_color=tag_col,
                cursor="hand2"
            )
            lbl_tag.pack(side="left", padx=2)

            for w in (card, inner, lbl_name, lbl_tag):
                w.bind("<ButtonPress-1>", lambda e, p=name: self.trigger_pitcher(p))

        for c in range(cols):
            self.bench_cards_frame.grid_columnconfigure(c, weight=1)

    def _on_bench_double_click(self, player_name: str):
        for i in range(1, 10):
            if not self.slot_players[i - 1]:
                self.assign_player_to_slot(i, player_name)
                return

    # ----------------------------------------------------------------
    # 전광판 스포트라이트 및 NEXT 타순 갱신
    # ----------------------------------------------------------------
    def _update_scoreboard_spotlight(self, player_name: str, is_pitcher: bool = False):
        folder = self.audio_dir_var.get().strip()
        meta = get_player_meta(player_name)

        self.current_spotlight_player = player_name
        self.current_spotlight_is_pitcher = is_pitcher

        if hasattr(self, "spotlight_walkup_button"):
            if is_pitcher:
                self.spotlight_walkup_button.configure(text="🎵 등판곡 틀기")
            else:
                self.spotlight_walkup_button.configure(text="🎵 등장곡 틀기")

        # 1. 3:4 세로 비율 사진/플레이스홀더 갱신 (240x320)
        pil_img = get_player_spotlight_image(folder, player_name, is_pitcher=is_pitcher, target_size=(240, 320))
        self.spotlight_ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(240, 320))
        self.spotlight_photo_lbl.configure(image=self.spotlight_ctk_img)

        # 2. 텍스트 정보 갱신 (왼쪽 하단 포지션 배지 + 우측 58pt 초대형 이름)
        if is_pitcher:
            self.spotlight_tag.configure(text="👑 ASHLEY QUEENS  |  ★ 마운드 등판 (NOW ON PITCHER) ★")
            pos_text = f"#{meta['num']}  |  {meta['role']} ({meta['pos_full']})  |  애슐리 마운드"
            self.lbl_spotlight_info.configure(text=pos_text)
            self.lbl_spotlight_track.configure(text=f"📁 투수_{player_name}_등장곡.mp3")
        else:
            slot_str = f"{self.current_batter_index}번 타자" if self.current_batter_index > 0 else "타자"
            pos_now = self.slot_positions[self.current_batter_index - 1] if self.current_batter_index > 0 else meta['pos']
            role_now = POSITION_ROLES.get(pos_now, meta['role'])
            if pos_now in meta['pos_full']:
                pos_display = meta['pos_full']
            else:
                pos_display = f"{pos_now} / {meta['pos_full']}"
            pos_text = f"#{meta['num']}  |  {role_now} ({pos_display})  |  {slot_str}"
            self.spotlight_tag.configure(text="👑 ASHLEY QUEENS  |  ★ 현재 타석 (NOW ON BATTER) ★")
            self.lbl_spotlight_info.configure(text=pos_text)
            self.lbl_spotlight_track.configure(text=f"📁 {player_name}_등장곡 / 응원가.mp3")

        self.lbl_spotlight_name.configure(text=player_name)

        # 3. NEXT 타순 갱신 및 야구장 다이아몬드 그래픽 갱신
        self._update_next_batters_display()
        self._update_baseball_field()

    def _update_next_batters_display(self):
        curr = self.current_batter_index if self.current_batter_index > 0 else 1
        for step in range(3):
            next_idx = ((curr - 1 + step + 1) % 9) + 1
            next_player = self.slot_players[next_idx - 1]
            pos_next = self.slot_positions[next_idx - 1]
            if next_player:
                meta = get_player_meta(next_player)
                self.next_batter_labels[step].configure(
                    text=f"{next_idx}번 #{meta['num']} {next_player} ({pos_next})",
                    fg_color="#3c1864",
                    text_color="#ffffff"
                )
            else:
                self.next_batter_labels[step].configure(
                    text=f"{next_idx}번 (미지정)",
                    fg_color="#1f0d36",
                    text_color="#95a5a6"
                )

    def _update_current_batter_ui(self):
        for i, lbl in enumerate(self.slot_order_labels):
            slot_num = i + 1
            frame = self.slot_frames[i]
            if slot_num == self.current_batter_index:
                lbl.configure(text=f"▶ {slot_num}번", text_color="#ffd166")
                frame.configure(border_color="#ffd166", border_width=2, fg_color="#3c1864")
            else:
                lbl.configure(text=f"{slot_num}번 [Alt+{slot_num}]", text_color="#ffffff")
                frame.configure(border_color="#3c1864", border_width=1, fg_color="#24103d" if slot_num % 2 == 1 else "#1e0c33")

    def _update_starter_cards(self):
        for name, widgets in self.starter_widgets.items():
            is_active = (name == self.current_pitcher)
            card = widgets["card"]
            tag_lbl = widgets["tag_lbl"]
            if is_active:
                card.configure(fg_color="#7209b7", border_color="#ffd166", border_width=2)
                tag_lbl.configure(text="🔥 등판 중", text_color="#ffd166")
            else:
                card.configure(fg_color="#1f0d36", border_color="#3c1864", border_width=1)
                tag_lbl.configure(text="[▶ 등판]", text_color="#ffd166")

    def _reload_starter_photos(self):
        folder = self.audio_dir_var.get().strip()
        for name, widgets in self.starter_widgets.items():
            pil_img = get_pitcher_photo(folder, name, target_size=(72, 72))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(72, 72))
            widgets["ctk_img"] = ctk_img
            widgets["photo_lbl"].configure(image=ctk_img)
        self._update_starter_cards()

    # ----------------------------------------------------------------
    # 오디오 경로 및 파일 확인
    # ----------------------------------------------------------------
    def _get_audio_paths(self, player_name: str) -> tuple[str, str]:
        folder = self.audio_dir_var.get().strip()
        name = player_name.strip()
        if not name:
            return "", ""
        walkup = os.path.join(folder, f"{name}_등장곡.mp3")
        cheer = os.path.join(folder, f"{name}_응원가.mp3")
        return walkup, cheer

    def _refresh_available_players(self):
        folder = self.audio_dir_var.get().strip()
        self.all_available_players.clear()
        self.all_available_pitchers.clear()

        if os.path.isdir(folder):
            try:
                for fname in os.listdir(folder):
                    if fname.lower().endswith(".mp3"):
                        if fname.startswith("투수_") and "_등장곡" in fname:
                            pname = fname[3:].split("_등장곡")[0].strip()
                            if pname:
                                self.all_available_pitchers.add(pname)
                        elif "_등장곡" in fname:
                            pname = fname.split("_등장곡")[0].strip()
                            if pname:
                                self.all_available_players.add(pname)
                        elif "_응원가" in fname:
                            pname = fname.split("_응원가")[0].strip()
                            if pname:
                                self.all_available_players.add(pname)
            except Exception as e:
                print(f"[폴더 스캔 에러]: {e}")

        # 전체 로스터 기본 등록
        for p in PLAYER_ROSTER:
            meta = PLAYER_ROSTER[p]
            if meta["role"] == "선발투수" or meta["role"] == "불펜투수" or meta["role"] == "마무리투수":
                self.all_available_pitchers.add(p)
            else:
                self.all_available_players.add(p)

        self._render_current_bench_tab()

    def _update_slot_indicator(self, slot_idx: int):
        walkup_badge, cheer_badge = self.slot_badges[slot_idx - 1]
        player_name = self.slot_players[slot_idx - 1]

        if not player_name:
            walkup_badge.configure(text="등장 ✗", fg_color="#301548", text_color="#95a5a6")
            cheer_badge.configure(text="응원 ✗", fg_color="#301548", text_color="#95a5a6")
            return

        walkup_file, cheer_file = self._get_audio_paths(player_name)
        has_walkup = bool(walkup_file and os.path.isfile(walkup_file))
        has_cheer = bool(cheer_file and os.path.isfile(cheer_file))

        if has_walkup:
            walkup_badge.configure(text="등장 ✓", fg_color="#1e3a29", text_color="#2ecc71")
        else:
            walkup_badge.configure(text="등장 ✗", fg_color="#301548", text_color="#95a5a6")

        if has_cheer:
            cheer_badge.configure(text="응원 ✓", fg_color="#1e3a29", text_color="#2ecc71")
        else:
            cheer_badge.configure(text="응원 ✗", fg_color="#301548", text_color="#95a5a6")

    # ----------------------------------------------------------------
    # 라인업 저장 및 복원
    # ----------------------------------------------------------------
    def _load_or_init_lineup(self):
        loaded = False
        if os.path.isfile(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    lineup = data.get("lineup", [])
                    if isinstance(lineup, list) and len(lineup) >= 9:
                        for i in range(9):
                            self._set_slot_player(i + 1, str(lineup[i]))
                        loaded = True
                    positions = data.get("positions", [])
                    if isinstance(positions, list) and len(positions) >= 9:
                        for i in range(9):
                            self.slot_positions[i] = str(positions[i])
                            self.slot_pos_menus[i].set(str(positions[i]))
                    saved_dir = data.get("audio_dir")
                    if saved_dir:
                        if not os.path.isabs(saved_dir):
                            resolved_dir = os.path.normpath(os.path.join(SCRIPT_DIR, saved_dir))
                        else:
                            resolved_dir = saved_dir
                        if os.path.isdir(resolved_dir):
                            self.audio_dir_var.set(resolved_dir)
                    saved_proc = data.get("process_name")
                    if saved_proc:
                        self.process_name_var.set(saved_proc)
                    saved_pitcher = data.get("active_pitcher")
                    if saved_pitcher:
                        self.current_pitcher = saved_pitcher
            except Exception as e:
                print(f"[설정 로드 실패]: {e}")

        if not loaded:
            for i in range(9):
                name = DEFAULT_LINEUP[i] if i < len(DEFAULT_LINEUP) else ""
                self._set_slot_player(i + 1, name)
                pos = DEFAULT_POSITIONS[i] if i < len(DEFAULT_POSITIONS) else "DH"
                self.slot_positions[i] = pos
                self.slot_pos_menus[i].set(pos)

        for i in range(1, 10):
            self._update_slot_indicator(i)

        self._render_current_bench_tab()
        self._update_starter_cards()
        self._update_baseball_field()
        if self.slot_players[0]:
            self._update_scoreboard_spotlight(self.slot_players[0], is_pitcher=False)

    def save_lineup(self, silent: bool = False):
        data = {
            "lineup": self.slot_players,
            "positions": self.slot_positions,
            "active_pitcher": self.current_pitcher,
            "audio_dir": self.audio_dir_var.get().strip(),
            "process_name": self.process_name_var.get().strip(),
            "focus_check": self.focus_check_var.get()
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if not silent:
                self.on_audio_status_update("💾 라인업과 설정이 성공적으로 저장되었습니다.", level="info")
        except Exception as e:
            if not silent:
                messagebox.showerror("저장 오류", f"라인업 저장 중 오류가 발생했습니다:\n{e}")

    # ----------------------------------------------------------------
    # 자동 투수 복귀 타이머 (노래 꺼지고 5초 무응답 시)
    # ----------------------------------------------------------------
    def _cancel_pitcher_revert_timer(self):
        """대기 중인 5초 자동 투수 복귀 타이머 취소"""
        if self.pitcher_revert_timer_id is not None:
            try:
                self.after_cancel(self.pitcher_revert_timer_id)
            except Exception:
                pass
            self.pitcher_revert_timer_id = None

    def _start_pitcher_revert_timer(self, delay_ms: int = 5000):
        """음악 종료 후 5초 무응답 시 투수로 자동 복귀하는 타이머 시작"""
        self._cancel_pitcher_revert_timer()
        self.pitcher_revert_timer_id = self.after(delay_ms, self._auto_revert_to_pitcher)

    def _auto_revert_to_pitcher(self):
        """5초 동안 무응답 시 스포트라이트/썸네일을 현재 선발투수로 자동 전환"""
        self.pitcher_revert_timer_id = None
        if self.audio_engine.is_playing:
            return
        if getattr(self, "current_spotlight_is_pitcher", False):
            return

        pitcher = self.current_pitcher or "권영호"
        self._update_scoreboard_spotlight(pitcher, is_pitcher=True)
        self._update_baseball_field()
        self.on_audio_status_update(f"⚾ [대기 모드] 5초 무응답으로 선발투수 {pitcher} 썸네일로 자동 전환되었습니다.", level="idle")

    # ----------------------------------------------------------------
    # 재생 및 단축키 트리거
    # ----------------------------------------------------------------
    def trigger_slot(self, slot_idx: int, cheer_only: bool = False):
        if slot_idx < 1 or slot_idx > 9:
            return

        self._cancel_pitcher_revert_timer()
        self.current_batter_index = slot_idx
        self._update_current_batter_ui()

        player_name = self.slot_players[slot_idx - 1]
        if not player_name:
            self.on_audio_status_update(f"⚠️ {slot_idx}번 타자 슬롯에 선수가 배치되지 않았습니다.", level="warning")
            return

        self._update_scoreboard_spotlight(player_name, is_pitcher=False)
        walkup_file, cheer_file = self._get_audio_paths(player_name)
        self.audio_engine.play_batter_sequence(slot_idx, player_name, walkup_file, cheer_file, cheer_only=cheer_only)

    def play_next_batter(self, cheer_only: bool = False):
        self._cancel_pitcher_revert_timer()
        if self.current_batter_index <= 0 or self.current_batter_index >= 9:
            next_idx = 1
        else:
            next_idx = self.current_batter_index + 1
        self.trigger_slot(next_idx, cheer_only=cheer_only)

    def trigger_pitcher(self, pitcher_name: str):
        self._cancel_pitcher_revert_timer()
        self.current_pitcher = pitcher_name
        folder = self.audio_dir_var.get().strip()
        walkup_file = os.path.join(folder, f"투수_{pitcher_name}_등장곡.mp3")

        # 이제임스 호환
        if not os.path.isfile(walkup_file) and pitcher_name == "이제임스":
            walkup_file = os.path.join(folder, "투수_제임스_등장곡.mp3")

        if not os.path.isfile(walkup_file):
            self.on_audio_status_update(f"⚠️ [투수 {pitcher_name}] 등장곡 파일이 없습니다.", level="warning")
            return

        self._update_scoreboard_spotlight(pitcher_name, is_pitcher=True)
        self.audio_engine.play_batter_sequence(
            slot_num=0,
            player_name=f"투수 {pitcher_name}",
            walkup_file=walkup_file,
            cheer_file="",
            crossfade_ms=1000,
            cheer_only=False
        )

        self._update_starter_cards()
        self._update_baseball_field()
        if hasattr(self, "bench_tab_selector") and "불펜" in self.bench_tab_selector.get():
            self._render_bench_pitchers()

        self.save_lineup(silent=True)

    def play_spotlight_walkup(self):
        """현재 스포트라이트(썸네일)에 표시된 선수의 등장곡만 즉시 재생"""
        self._cancel_pitcher_revert_timer()
        player_name = getattr(self, "current_spotlight_player", "")
        if not player_name:
            if self.slot_players and self.slot_players[0]:
                player_name = self.slot_players[0]
            else:
                return

        is_pitcher = getattr(self, "current_spotlight_is_pitcher", False)
        folder = self.audio_dir_var.get().strip()

        if is_pitcher:
            self.trigger_pitcher(player_name)
        else:
            walkup_file, cheer_file = self._get_audio_paths(player_name)
            if not walkup_file or not os.path.isfile(walkup_file):
                if cheer_file and os.path.isfile(cheer_file):
                    self.on_audio_status_update(f"ℹ️ [{player_name}] 등장곡이 없어 응원가로 재생합니다.", level="info")
                    walkup_file = ""
                else:
                    self.on_audio_status_update(f"⚠️ [{player_name}] 등장곡 음원 파일이 없습니다.", level="warning")
                    return

            slot_idx = 0
            if player_name in self.slot_players:
                slot_idx = self.slot_players.index(player_name) + 1

            self._update_scoreboard_spotlight(player_name, is_pitcher=False)
            self.audio_engine.play_batter_sequence(
                slot_num=slot_idx,
                player_name=player_name,
                walkup_file=walkup_file,
                cheer_file="",  # 등장곡만 재생 (응원가 제외)
                crossfade_ms=1000,
                cheer_only=False
            )

    def stop_playback(self):
        self._cancel_pitcher_revert_timer()
        self.audio_engine.stop(reason="모든 오디오 즉시 정지")

    def fadeout_playback(self):
        self._cancel_pitcher_revert_timer()
        self.audio_engine.fadeout(duration_ms=1500, reason="타자 아웃! 페이드아웃")

    # ----------------------------------------------------------------
    # 글로벌 및 로컬 단축키 제어 (하드웨어 레벨 직접 감지)
    # ----------------------------------------------------------------
    def _register_global_hotkeys(self):
        # 1. Tkinter 로컬 키 바인딩 (본 프로그램 창에 포커스가 있을 때도 즉각 반응)
        for i in range(1, 10):
            self.bind_all(f"<Alt-Key-{i}>", lambda e, idx=i: self._on_hotkey_pressed(idx))
            self.bind_all(f"<Shift-Key-{i}>", lambda e, idx=i: self._on_cheer_hotkey_pressed(idx))
        self.bind_all("<Alt-Key-0>", lambda e: self._on_out_hotkey_pressed())
        self.bind_all("<Alt-p>", lambda e: self._on_pitcher_hotkey_pressed())
        self.bind_all("<Alt-P>", lambda e: self._on_pitcher_hotkey_pressed())
        self.bind_all("<Alt-grave>", lambda e: self._on_next_hotkey_pressed())
        self.bind_all("<Alt-asciitilde>", lambda e: self._on_next_hotkey_pressed())
        self.bind_all("<Shift-grave>", lambda e: self._on_next_cheer_hotkey_pressed())
        self.bind_all("<Shift-asciitilde>", lambda e: self._on_next_cheer_hotkey_pressed())

        # 2. 로우레벨 키보드 훅 등록:
        # win32api.GetAsyncKeyState()를 통해 OS 커널에서 Alt/Shift/Ctrl 물리적 눌림 상태를 직접 조회하여
        # KeyUp 누락이나 창 전환(Alt-Tab), 한글 IME 등으로 인한 키보드 먹통 버그를 100% 방지합니다.
        try:
            keyboard.hook(self._on_global_raw_key)
        except Exception as e:
            print(f"[글로벌 키보드 훅 등록 에러]: {e}")

    def _check_focus_condition(self) -> bool:
        if not self.focus_check_var.get():
            return True
        target_proc = self.process_name_var.get().strip()
        return is_process_focused(target_proc)

    def _on_global_raw_key(self, event):
        if event.event_type != "down":
            return

        try:
            # 0x12: VK_MENU (Alt), 0x10: VK_SHIFT, 0x11: VK_CONTROL
            is_alt = bool(win32api.GetAsyncKeyState(0x12) & 0x8000)
            is_shift = bool(win32api.GetAsyncKeyState(0x10) & 0x8000)
            is_ctrl = bool(win32api.GetAsyncKeyState(0x11) & 0x8000)
        except Exception:
            is_alt = False
            is_shift = False
            is_ctrl = False

        if is_ctrl:
            return

        if not is_alt and not is_shift:
            return

        # 포커스 검사 (체크박스 해제 시 통과, 게임 또는 본 앱 창 포커스 시 통과)
        if not self._check_focus_condition():
            return

        scan = event.scan_code
        name = (event.name or "").lower()

        # 숫자 키 스캔코드 매핑 (상단 숫자키 2~10, 넘패드 79,80,81,75,76,77,71,72,73)
        scan_to_slot = {
            2: 1, 79: 1,
            3: 2, 80: 2,
            4: 3, 81: 3,
            5: 4, 75: 4,
            6: 5, 76: 5,
            7: 6, 77: 6,
            8: 7, 71: 7,
            9: 8, 72: 8,
            10: 9, 73: 9
        }

        # 1. Alt 조합 키
        if is_alt and not is_shift:
            # Alt + ` (Next 타자 자동재생) - scan code 41
            if scan == 41 or name in ("`", "grave", "~", "asciitilde"):
                self._on_next_hotkey_pressed()
                return

            # Alt + 0 (아웃 / 페이드아웃) - scan code 11 또는 넘패드 82
            if scan in (11, 82) or name == "0":
                self._on_out_hotkey_pressed()
                return

            # Alt + P (투수 등장곡) - scan code 25, 57369 또는 p, 한글 모드 'ㅔ'
            if scan in (25, 57369) or name in ("p", "ㅔ"):
                self._on_pitcher_hotkey_pressed()
                return

            # Alt + 1~9
            if scan in scan_to_slot:
                self._on_hotkey_pressed(scan_to_slot[scan])
                return
            elif name in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
                self._on_hotkey_pressed(int(name))
                return

        # 2. Shift 조합 키
        elif is_shift and not is_alt:
            # Shift + ` (Next 타자 응원가만 즉시재생)
            if scan == 41 or name in ("`", "grave", "~", "asciitilde"):
                self._on_next_cheer_hotkey_pressed()
                return

            # Shift + 1~9 (해당 타자 응원가만 즉시재생)
            if scan in scan_to_slot:
                self._on_cheer_hotkey_pressed(scan_to_slot[scan])
                return
            elif name in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
                self._on_cheer_hotkey_pressed(int(name))
                return

    def _on_hotkey_pressed(self, slot_idx: int):
        now = time.time()
        if now - self.last_hotkey_time < 0.25:
            return
        self.last_hotkey_time = now
        self.after(0, lambda: self.trigger_slot(slot_idx, cheer_only=False))

    def _on_cheer_hotkey_pressed(self, slot_idx: int):
        now = time.time()
        if now - self.last_hotkey_time < 0.25:
            return
        self.last_hotkey_time = now
        self.after(0, lambda: self.trigger_slot(slot_idx, cheer_only=True))

    def _on_next_hotkey_pressed(self):
        now = time.time()
        if now - self.last_next_hotkey_time < 0.3:
            return
        self.last_next_hotkey_time = now
        self.after(0, lambda: self.play_next_batter(cheer_only=False))

    def _on_next_cheer_hotkey_pressed(self):
        now = time.time()
        if now - self.last_next_cheer_hotkey_time < 0.3:
            return
        self.last_next_cheer_hotkey_time = now
        self.after(0, lambda: self.play_next_batter(cheer_only=True))

    def _on_pitcher_hotkey_pressed(self):
        now = time.time()
        if now - self.last_pitcher_hotkey_time < 0.3:
            return
        self.last_pitcher_hotkey_time = now

        target = self.current_pitcher
        if not target:
            sorted_pitchers = sorted(list(self.all_available_pitchers))
            if sorted_pitchers:
                target = sorted_pitchers[0]
            else:
                target = "권영호"

        if target:
            self.after(0, lambda: self.trigger_pitcher(target))

    def _on_out_hotkey_pressed(self):
        now = time.time()
        if now - self.last_hotkey_time < 0.25:
            return
        self.last_hotkey_time = now
        self.after(0, self.fadeout_playback)

    # ----------------------------------------------------------------
    # 상태 갱신 및 타이머 콜백
    # ----------------------------------------------------------------
    def on_audio_status_update(self, message: str, level: str = "info"):
        colors = {
            "walkup": "#ffd166",
            "waiting": "#f39c12",
            "cheer": "#06d6a0",
            "stopped": "#ef233c",
            "warning": "#f39c12",
            "error": "#ef233c",
            "idle": "#ffffff"
        }
        color = colors.get(level, "#ffffff")
        self.after(0, lambda: self.status_icon_label.configure(text=message, text_color=color))

        # 노래가 꺼지거나 완료되면 5초 무응답 시 선발투수 썸네일로 자동 전환
        if level in ("idle", "stopped"):
            if not getattr(self, "current_spotlight_is_pitcher", False):
                self._start_pitcher_revert_timer(5000)
        elif level in ("walkup", "cheer", "waiting"):
            self._cancel_pitcher_revert_timer()

    def _schedule_game_status_check(self):
        target_proc = self.process_name_var.get().strip()
        text, color = get_game_status_text(target_proc)
        self.game_status_badge.configure(text=f"🎮 {text}", text_color=color)
        self.after(1000, self._schedule_game_status_check)

    def _on_volume_change(self, value):
        volume = float(value) / 100.0
        self.audio_engine.set_volume(volume)
        self.volume_label.configure(text=f"🔊 볼륨: {int(value)}%")

    def _browse_audio_dir(self):
        selected = filedialog.askdirectory(initialdir=self.audio_dir_var.get(), title="응원가 음원 폴더 선택")
        if selected:
            self.audio_dir_var.set(selected)
            self._refresh_available_players()
            self._reload_starter_photos()
            for i in range(1, 10):
                self._update_slot_indicator(i)

    def on_closing(self):
        self._cancel_pitcher_revert_timer()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.audio_engine.stop(reason="애플리케이션 종료")
        self.save_lineup(silent=True)
        self.destroy()


# ====================================================================
# 프로그램 시작점
# ====================================================================
if __name__ == "__main__":
    app = SMB4CheerPlayerApp()
    app.mainloop()
