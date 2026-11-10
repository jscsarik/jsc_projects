# 🎙️ Discord Auto Mute (음성인식 자동 음소거 매니저)

> **게임이나 작업 도중 손을 쓰지 않고 목소리만으로 Discord 마이크 음소거 및 통화 종료를 제어하는 핸즈프리 유틸리티**  
> 백그라운드에서 마이크 입력을 분석하여 특정 음성 명령을 감지하면 디스코드의 글로벌 단축키를 자동으로 호출합니다.

---

## 📌 주요 기능

- 🗣️ **음성 명령 인식 (Speech Recognition)**
  - `"마이크 오프"`, `"마이크 꺼줘"`: 마이크 즉시 음소거/음소거 해제 토글
  - `"좀 있다 올게"`, `"나갈게"`: 음성 채널 즉시 연결 종료 (통화 방 나가기)
- 🔕 **스마트 백그라운드 실행**
  - VBScript 런처(`launcher.vbs`)를 통해 콘솔 검은 창 없이 무음 백그라운드로 조용하게 실행
- 🎯 **자동 디스코드 감지**
  - **Discord Canary** 및 **정식 Discord** 설치 경로를 자동 탐색하여 프로그램과 함께 실행
- 🚀 **원클릭 바로가기 생성**
  - `create_shortcut.py`를 통해 공식 디스코드 아이콘이 적용된 바로가기 자동 생성

---

## 🛠️ 기술 스택

- **Language**: Python 3.10+ (추천: Python 3.12/3.13)
- **Speech Engine**: `SpeechRecognition` (Google Speech API 연동), `PyAudio`
- **System Control**: `keyboard`, `win32gui`, `win32com`, `psutil`
- **Packaging**: PyInstaller, VBScript

---

## ⚙️ 사전 설정 (Discord 단축키 매핑)

본 프로그램이 디스코드를 제어할 수 있도록 Discord 설정에서 글로벌 단축키를 먼저 등록해야 합니다.

1. Discord 실행 후 좌측 하단 **[사용자 설정(톱니바퀴)] ➔ [단축키]** 이동
2. **[단축키 추가하기]** 클릭 후 아래 두 개의 단축키 등록:
   - **동작**: `마이크 음소거 전환` / **단축키**: `Ctrl + PageDown`
   - **동작**: `음성 채널 연결 끊기` / **단축키**: `Ctrl + PageUp`

---

## 🚀 설치 및 실행 방법

### 1. 필수 라이브러리 설치
```bash
pip install speechrecognition keyboard psutil pywin32 pyaudio
```
> [!TIP]
> 만약 Windows에서 `pyaudio` 설치 시 오류가 발생한다면, `pip install pipwin` 후 `pipwin install pyaudio`를 실행하거나 사전 빌드된 wheel 파일을 사용하세요.

### 2. 바로가기 생성
```bash
python create_shortcut.py
```
폴더 내에 `Discord Canary (음성인식).lnk` 바로가기가 생성됩니다.

### 3. 프로그램 실행
- 생성된 바로가기를 더블 클릭하거나 `launcher.vbs`를 실행하면 Discord와 음성인식 매니저가 백그라운드에서 동시에 켜집니다.
- 디버깅용으로 콘솔에서 직접 실행하려면:
  ```bash
  python discord_mute.py
  ```

---

## 📂 프로젝트 구조

```text
├── discord_mute.py          # 음성 인식 및 단축키 전송 메인 로직
├── launcher.vbs             # 백그라운드 무음 실행 런처
├── create_shortcut.py       # 아이콘 연동 바로가기 파일 자동 생성기
├── discord_mute.spec        # PyInstaller 단일 실행파일 빌드 스펙
├── discord_mute_debug.spec  # PyInstaller 디버그 빌드 스펙
└── .gitignore               # 캐시 및 빌드 결과물 제외 설정
```
