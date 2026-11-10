# 🤖 byungsans (병Sans 디스코드 음악·ASMR·게임 봇)

> **라즈베리파이(PM2) 상에서 24시간 무중단 상주 구동되는 다기능 디스코드 오디오 봇**  
> 유튜브 고음질 음악 스트리밍(`yt-dlp`), 24/7 JSC 무한 라디오 방송국, 큐(Queue) 대기열 관리, 음성 채널 자동 자원 절약(Self-Deaf), 훈민정음 어휘 데이터베이스를 내장한 디스코드 봇 엔진입니다.

---

## 📌 주요 특징 (Key Features)

- 🎵 **유튜브 스트리밍 & 대기열 시스템 (`yt-dlp` + `ffmpeg`)**
  - 곡 제목 또는 유튜브 링크를 입력하면 `yt-dlp`를 통해 최적 오디오 스트림을 추출하여 실시간 재생합니다.
  - 다음 곡들을 순차적으로 대기열(Queue)에 적재하고 `!skip`, `!stop`, `!q` 명령어로 유연하게 제어합니다.
- 📻 **JSC 24/7 무한 라디오 송출 (`!무한`)**
  - 별도 선곡 없이도 고음질 라디오 방송국을 24시간 끊김 없이 음성 채널에 스트리밍합니다.
- 🤫 **히든 힐링 ASMR & 비밀 커맨드**
  - 수면 유도 및 휴식을 위한 엄선된 ASMR 프리셋 및 히든 명령어를 내장하고 있습니다.
- 🛡️ **스마트 음성 자원 최적화 (`ensure_deaf`)**
  - 봇이 음성 채널에 접속하는 즉시 자동으로 자체 귀막기(`self_deaf=True`) 상태로 전환하여 라즈베리파이의 네트워크 대역폭과 CPU 연산량을 획기적으로 절약합니다.
- 📚 **훈민정음 사전 데이터베이스 (`hunminjeongeum_words/`)**
  - 19개 분류별 국어 어휘 텍스트 데이터를 탑재하여 단어 퀴즈 및 게임을 지원합니다.
- 🍓 **라즈베리파이 PM2 완벽 호환**
  - 저전력 라즈베리파이(Debian aarch64) 환경에서 PM2 프로세스 매니저를 통해 예기치 못한 네트워크 단절이나 크래시 발생 시 즉각 자동 복구됩니다.

---

## 🛠️ 기술 스택 (Tech Stack)

- **Language**: Python 3.10+
- **Discord API**: `discord.py` (v2.3+)
- **Audio Extraction**: `yt-dlp`
- **Voice Encoding**: `PyNaCl`, `FFmpeg`
- **Environment**: `python-dotenv`
- **Server Platform**: Raspberry Pi (Debian aarch64, PM2)

---

## 💡 명령어 안내 (Commands Guide)

| 명령어 | 매개변수 | 동작 설명 |
| :--- | :--- | :--- |
| **`!play`** | `[곡제목 또는 유튜브 링크]` | 유튜브에서 검색하여 음성 채널에서 즉시 재생하거나 대기열에 추가합니다. |
| **`!무한`** | - | JSC 24/7 고음질 라디오 방송국을 무한 송출 모드로 전환합니다. |
| **`!q`** | - | 현재 예약된 노래 대기열 목록을 임베드로 확인합니다. |
| **`!skip`** | - | 현재 재생 중인 노래를 건너뛰고 다음 곡으로 넘어갑니다. |
| **`!stop`** | - | 재생을 중단하고 대기열을 모두 비운 뒤 음성 채널에서 퇴장합니다. |
| **`!join`** | - | 명령어를 입력한 유저가 접속 중인 음성 채널로 봇을 호출합니다. |
| **`!help`** | - | 봇의 전체 명령어 가이드와 숨겨진 힌트를 확인합니다. |

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Python 3.10 이상
- `ffmpeg` (시스템 PATH에 등록되어 있어야 함)
  - Ubuntu / Raspberry Pi OS: `sudo apt update && sudo apt install -y ffmpeg`
  - Windows: `winget install Gyan.FFmpeg` 또는 수동 설치 후 환경변수 등록

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 Discord Bot Token을 설정합니다 (또는 `token.txt` 파일에 토큰 기입).
```bash
cp .env.example .env
```
```env
DISCORD_BOT_TOKEN="your_discord_bot_token_here"
```

### 4. 봇 실행

#### 로컬 환경에서 실행
```bash
python bot.py
# 또는 Windows의 경우: bot_start.bat
```

#### 라즈베리파이 PM2 서비스로 상주 실행
```bash
pm2 start bot.py --name byungsans --interpreter python3
pm2 save
```

---

## 📂 프로젝트 구조

```text
byungsans/
├── hunminjeongeum_words/       # 훈민정음 및 단어 게임용 국어 어휘 데이터베이스 (19개 사전 파일)
├── bot.py                      # yt-dlp 기반 유튜브 스트리밍, 대기열, 음성 제어 메인 봇 스크립트
├── bot_start.bat               # Windows 환경 간편 실행 배치파일
├── 병Sans_디스코드봇_실행방법.txt # 초보자용 실행 가이드 문서
├── requirements.txt            # 필수 파이썬 패키지 목록
├── .env.example                # 봇 토큰 환경변수 템플릿
├── .gitignore                  # 토큰 및 바이너리 제외 규칙
└── README.md                   # 시스템 매뉴얼 (현재 파일)
```
