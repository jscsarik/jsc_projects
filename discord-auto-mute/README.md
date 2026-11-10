# 🎙️ Discord Auto Mute (음성인식 기반 Discord 자동 음소거 매니저)

> **게임이나 업무 중 손을 쓰지 않고 목소리만으로 Discord 마이크 음소거 및 통화 종료를 제어하는 핸즈프리 유틸리티**  
> 백그라운드에서 마이크 입력을 상시 모니터링하여 음성 명령을 감지하면, 디스코드의 글로벌 단축키를 자동으로 호출하여 동작합니다.

---

## 📌 주요 특징 (Key Features)

- 🗣️ **정밀한 음성 명령 인식 (Speech Recognition)**
  - `"마이크 오프"` / `"마이크 꺼줘"`: 마이크 즉시 음소거/음소거 해제 토글 (`Ctrl + PageDown`)
  - `"좀 있다 올게"` / `"나갈게"`: 음성 채널 즉시 연결 종료 (`Ctrl + PageUp`)
- 🔕 **무음 백그라운드 런처 (VBScript)**
  - `launcher.vbs`를 통해 번거로운 검은색 CMD 창 없이 백그라운드에서 조용하게 실행
- 🎯 **Discord & Discord Canary 자동 감지**
  - 시스템에 설치된 Discord 정식 버전 및 Canary 버전을 자동 탐색하여 프로그램과 함께 원클릭 동시 기동
- 🚀 **원클릭 공식 아이콘 바로가기 자동 생성**
  - `create_shortcut.py`를 통해 공식 Discord 아이콘이 입혀진 윈도우 바로가기 파일 자동 생성

---

## 🛠️ 기술 스택 (Tech Stack)

- **Language**: Python 3.10+ (추천: Python 3.12 / 3.13)
- **Speech Engine**: `SpeechRecognition` (Google Speech API), `PyAudio`
- **System Automation**: `keyboard`, `win32gui`, `win32com`, `psutil`
- **Packaging & Launch**: PyInstaller, VBScript

---

## ⚙️ 사전 설정 (Discord 글로벌 단축키 등록)

프로그램이 Discord를 백그라운드에서 제어할 수 있도록 Discord 설정에서 글로벌 단축키를 먼저 등록해야 합니다.

1. Discord 실행 후 좌측 하단 **[사용자 설정(톱니바퀴)] ➔ [단축키]**로 이동합니다.
2. **[단축키 추가하기]** 버튼을 클릭하여 아래 두 항목을 등록합니다:
   - **동작**: `마이크 음소거 전환` / **단축키**: `Ctrl + PageDown`
   - **동작**: `음성 채널 연결 끊기` / **단축키**: `Ctrl + PageUp`

---

## 🚀 빠른 시작 (Getting Started)

### 1. 필수 라이브러리 설치
```bash
pip install speechrecognition keyboard psutil pywin32 pyaudio
```
> [!TIP]  
> Windows 환경에서 `pyaudio` 설치 시 컴파일러 오류가 발생할 경우:  
> `pip install pipwin` 실행 후 `pipwin install pyaudio` 명령어를 입력하세요.

### 2. 바로가기 생성
```bash
python create_shortcut.py
```
폴더 내에 `Discord Canary (음성인식).lnk` 바로가기 파일이 생성됩니다.

### 3. 프로그램 실행
- 생성된 바로가기를 더블 클릭하거나 `launcher.vbs`를 실행하면 Discord와 음성인식 매니저가 백그라운드에서 동시에 켜집니다.
- 디버깅용으로 콘솔 로그를 보며 실행하려면:
  ```bash
  python discord_mute.py
  ```

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── discord_mute.py          # 마이크 음성 감지 및 단축키 트리거 메인 엔진
├── launcher.vbs             # CMD 창 없는 백그라운드 무음 실행 런처
├── create_shortcut.py       # Discord 아이콘 연동 바로가기 자동 생성기
├── discord_mute.spec        # PyInstaller 단일 실행파일 빌드 구성
├── discord_mute_debug.spec  # PyInstaller 디버그 모드 빌드 구성
└── README.md
```
