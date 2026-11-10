# 🎮 JuJe Bot Engine (주제어 디스코드 파티게임 봇 백엔드 엔진)

> **라즈베리파이(PM2 `juje-bot`)에서 24시간 무중단 구동되는 주제어 디스코드 파티게임 통합 관제 엔진**  
> 🌐 **공식 룰북 및 가이드 (Vercel):** [https://juje-bot.vercel.app/](https://juje-bot.vercel.app/)  
> 주제어 서바이벌, 3라운드 라이어, 바보 라이어, 텔레파시, 제로섬 데스매치, 칼전, 탐정 추리, 영웅시장, 지하철 서바이벌 등 9종 이상의 멀티플레이어 보드게임을 실시간 자동 진행하는 8,290줄 규모의 풀스케일 파이썬 디스코드 봇 서버입니다.

---

## 📌 주요 특징 (Key Features)

- 🗣️ **9대 멀티플레이어 보드게임 자동 관제 엔진**
  - **주제어 서바이벌**: 기본 7초 제한, 15턴 이상 돌파 시 5초 폭주 타이머 및 중복 단어/시간초과 자동 탈락 판정
  - **3라운드 라이어**: 봇 개인 DM으로 시민/라이어 제시어 분배, 순차 발언 페이즈, 지목 투표 및 3차 처형/역전 정답 판정
  - **바보 라이어**: 모두가 단어를 받지만 1명만 유사 단어를 받는 블라인드 마피아 게임
  - **텔레파시**: 주인공의 선택을 예측하여 목숨(❤️)을 걸고 생존하는 공감 & 눈치 게임
  - **제로섬 데스매치 / 칼전**: 상성과 체력 배분을 이용한 1:1 / 다대다 심리 배틀
  - **탐정 추리 & 비밀소설**: 장소와 단서 텍스트 데이터(`탐정/장소.txt`, `stage.txt`)를 기반으로 한 범인 추적
  - **영웅시장 (Hero Market)**: 실시간 시세 변동과 거래 로그(`HeroName.txt`) 기반의 경제 시뮬레이션
- 🎵 **게임 상황별 맞춤 사운드트랙 & 효과음 자동 믹싱 (FFmpeg)**
  - 인트로(`intro.mp3`), 긴장 타이머(`timer.mp3`), 처형(`Liar.mp3`), 최후 판정(`judgment.mp3`) 및 게임별 전용 BGM 폴더(`Kingdum_bgm`, `novel`, `sechan_bgm`, `subway`, `영웅시장`)를 음성 채널에 완벽히 동기화하여 스트리밍합니다.
- 🍓 **라즈베리파이 & Windows 크로스 플랫폼 최적화**
  - OS 자동 감지(`os.name`)를 통해 Windows에서는 `/`, Linux(라즈베리파이)에서는 `!` 접두사를 유연하게 적용합니다.
  - 라즈베리파이 PM2 프로세스 매니저 환경에서 75MB 내외의 초경량 메모리로 24시간 365일 무중단 운영됩니다.

---

## 🛠️ 기술 스택 (Tech Stack)

- **Language**: Python 3.10+
- **Discord Bot Framework**: `discord.py` (v2.3+)
- **Audio & Media**: `FFmpeg`, `PyNaCl` (Voice Gateway v4), `yt-dlp`
- **Image Processing**: `Pillow` (노선도 및 게임 보드 이미지 연동)
- **Environment**: `python-dotenv`
- **Hosting / Deployment**: Raspberry Pi (Debian aarch64, PM2)

---

## 💡 주요 게임 명령어 안내

| 명령어 | 매개변수 | 설명 |
| :--- | :--- | :--- |
| **`!서바이벌`** | `[주제]` | 주제어 릴레이 서바이벌 게임을 시작합니다. |
| **`!라이어`** | `[인원수]` | 3라운드 승점제 라이어 게임을 시작하고 DM으로 역할을 배정합니다. |
| **`!바보라이어`** | - | 플레이어 전원에게 블라인드 단어를 배분하는 바보 라이어 게임을 시작합니다. |
| **`!텔레파시`** | `[@유저]` | 지정된 유저를 주인공으로 하는 텔레파시 예측 게임을 시작합니다. |
| **`!제로섬`** | `[@상대]` | 체력 5를 걸고 진행하는 1:1 제로섬 데스매치를 시작합니다. |
| **`!영웅문`** | - | 영웅시장 거래 시뮬레이션 게임을 시작합니다. |
| **`!추리`** | - | 단서 기반 탐정 추리 모드를 시작합니다. |
| **`!스톱` / `!강제종료`** | - | 현재 채널에서 진행 중인 게임과 음원 재생을 즉시 강제 종료합니다. |

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Python 3.10 이상
- `ffmpeg` (시스템 환경변수 PATH 등록 필수)
  - Raspberry Pi / Linux: `sudo apt update && sudo apt install -y ffmpeg`
  - Windows: `winget install Gyan.FFmpeg`

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 디스코드 봇 토큰을 입력합니다 (또는 `토큰.txt` 파일 생성).
```bash
cp .env.example .env
```
```env
DISCORD_BOT_TOKEN="your_discord_bot_token_here"
```

### 4. 봇 실행

#### 로컬 환경에서 테스트
```bash
python main.py
```

#### 라즈베리파이 PM2 서비스 등록 및 상주 구동
```bash
pm2 start main.py --name juje-bot --interpreter python3
pm2 save
```

---

## 📂 프로젝트 구조

```text
juje-bot-engine/
├── Kingdum_bgm/              # 킹덤 테마 미니게임 전용 배경음악
├── novel/                    # 비밀소설 추리 게임 텍스트 데이터 및 BGM
├── sechan_bgm/               # 범용 세션 및 대기실 배경음악
├── subway/                   # 지하철 서바이벌 노선 데이터 및 오디오
├── 라이어주제/                # 라이어 게임 카테고리별 단어 사전 (과일, 동물, 영화 등)
├── 비밀소설테마/              # 소설 모드 전용 텍스트 프리셋
├── 영웅시장/                  # 영웅시장 시세표 및 음원 에셋
├── 주제/                      # 주제어 서바이벌용 대용량 키워드 리스트
├── 탐정/                      # 탐정 추리 게임 장소(`장소.txt`) 및 스테이지 데이터
├── main.py                   # 9개 게임 통합 관제 메인 디스코드 봇 엔진 (8,290줄)
├── intro.mp3 / Liar.mp3 ...  # 게임 공통 효과음 (타이머, 처형, 판정, BGM)
├── HeroName.txt              # 영웅 캐릭터 메타데이터
├── subway_map.png            # 지하철 맵 그래픽
├── telepathy.txt             # 텔레파시 질문 프리셋 데이터
├── requirements.txt          # 파이썬 의존성 패키지 목록
├── .env.example              # 봇 토큰 환경변수 템플릿
├── .gitignore                # 보안 토큰 및 바이너리 제외 규칙
└── README.md                 # 시스템 종합 매뉴얼 (현재 파일)
```
