# 🌌 Antigravity Workspace Monorepo

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Node.js](https://img.shields.io/badge/Node.js-20+-68a063?logo=node.js&logoColor=white)](https://nodejs.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178c6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Google Gemini](https://img.shields.io/badge/Google%20Gemini-LLM-4285f4?logo=google&logoColor=white)](https://aistudio.google.com/)
[![Supabase](https://img.shields.io/badge/Supabase-Realtime-3ecf8e?logo=supabase&logoColor=white)](https://supabase.com/)

> **Antigravity 환경에서 개발된 웹 애플리케이션, 인공지능 시뮬레이터, 데스크톱 유틸리티 및 시스템 도구를 한곳에 집약한 올인원 모노레포(Monorepo) 워크스페이스입니다.**

---

## 🏛️ 시스템 아키텍처 다이어그램

```mermaid
flowchart TD
    subgraph Client ["🖥️ Client / Frontends"]
        BCG["🎬 broadcast-cg-fun<br/>(OBS Overlay & Remote)"]
        JUJE["🎯 juje-web<br/>(Party Game Client)"]
        CHAT["🔒 private-chat-app<br/>(Secure Chat)"]
        TRPG["🐉 trpg-master-ai<br/>(Interactive AI TRPG)"]
    end

    subgraph BackendServices ["☁️ Cloud & AI Services"]
        SUPA[("⚡ Supabase Realtime<br/>WebSockets & DB")]
        GEMINI["🤖 Google Gemini LLM<br/>(Story & Rule Arbiter)"]
    end

    subgraph DesktopTools ["💻 Desktop & System Utilities"]
        DISCORD["🎙️ discord-auto-mute<br/>(Voice-activated Discord Control)"]
        SEARCH["🔍 win-search-tool<br/>(Watchdog Tray File Search)"]
        VMON["🖥️ virtual-monitor-tools<br/>(Virtual Display Driver Diagnostics)"]
    end

    BCG <-->|Realtime Sync| SUPA
    JUJE <-->|Realtime Sync| SUPA
    CHAT <-->|Realtime & Auth| SUPA
    TRPG <-->|Prompt & Stream| GEMINI
    TRPG <-->|Session Sync| SUPA
```

---

## 📑 포함된 프로젝트 목록 (Projects Overview)

| 프로젝트명 | 분야 | 주요 기술 스택 | 핵심 설명 | 바로가기 |
| :--- | :---: | :--- | :--- | :---: |
| [**`trpg-master-ai`**](./trpg-master-ai/) | **AI / Web** | Next.js 16, React 19, Google Gemini LLM, TailwindCSS, Supabase | D&D 5e 공식 룰셋과 창작 시나리오(군웅할거, 수미상관 등)를 기반으로 세션을 자율 진행하는 인터랙티브 TRPG 마스터 | [README](./trpg-master-ai/README.md) |
| [**`broadcast-cg-fun`**](./broadcast-cg-fun/) | **Web / Media** | Next.js, React, Supabase Realtime, `react-player` | OBS 방송 화면 자막/영상 오버레이(`/screen`)와 스마트폰 원격 제어기(`/remote`), TTS를 실시간 연동하는 방송 솔루션 | [README](./broadcast-cg-fun/README.md) |
| [**`juje-web`**](./juje-web/) | **Web / Game** | Next.js 16, React 19, Supabase Realtime, TailwindCSS v4 | 실시간 룸 생성, 라이어/추리 모드, 타이머 및 상황별 사운드 이펙트를 제공하는 보드게임 웹 클라이언트 | [README](./juje-web/README.md) |
| [**`private-chat-app`**](./private-chat-app/) | **Web / Chat** | Vite, React 19, TypeScript, Supabase Auth/Realtime, Oxlint | 초경량 고속 빌드 기반의 프라이빗 실시간 암호화 대화 및 알림음 지원 채팅 웹 | [README](./private-chat-app/README.md) |
| [**`discord-auto-mute`**](./discord-auto-mute/) | **Desktop** | Python 3, `speech_recognition`, `pyaudio`, `pywin32`, `keyboard` | 마이크 음성을 인식하여 게임 중 손대지 않고 디스코드 음소거 및 통화 종료를 자동 실행하는 백그라운드 런처 | [README](./discord-auto-mute/README.md) |
| [**`win-search-tool`**](./win-search-tool/) | **Desktop** | Python 3, Tkinter, `watchdog`, `chardet`, PyInstaller | Windows 시스템 트레이에 상주하며 로컬 문서의 텍스트 본문과 파일명을 초고속 실시간 검색하는 데스크톱 툴 | [README](./win-search-tool/README.md) |
| [**`virtual-monitor-tools`**](./virtual-monitor-tools/) | **System** | Python (`mss`), PowerShell, Windows Driver | 가상 디스플레이(Virtual Display Driver)의 활성화 여부를 진단하고 UAC 권한으로 복구하는 시스템 도구 모음 | [README](./virtual-monitor-tools/README.md) |

---

## 📁 디렉토리 구조 (Directory Structure)

```text
antigravity-workspace/
├── 📄 .gitignore                 # 보안 토큰, 캐시, OS 파일 완벽 차단
├── 📄 README.md                  # 전체 프로젝트 허브 문서 (현재 파일)
│
├── 📂 broadcast-cg-fun/          # 실시간 방송 CG 오버레이 & 리모컨 (Next.js)
│   ├── app/                      # /screen(OBS 뷰), /remote(리모컨), /api/tts
│   ├── .env.example              # Supabase 환경변수 템플릿
│   └── README.md
│
├── 📂 discord-auto-mute/         # 음성인식 Discord 자동 음소거 매니저 (Python)
│   ├── discord_mute.py           # 음성인식 메인 루프
│   ├── launcher.vbs              # 백그라운드 무음 실행 런처
│   └── README.md
│
├── 📂 juje-web/                  # '주제어' 추리 파티게임 웹 클라이언트 (Next.js 16)
│   ├── app/                      # 실시간 멀티플레이 로비 & 인게임 UI
│   ├── .env.example
│   └── README.md
│
├── 📂 private-chat-app/          # 초경량 실시간 보안 채팅 웹 (Vite + React 19)
│   ├── src/                      # Auth, Chat 컴포넌트 & 오디오 매니저
│   ├── .env.example
│   └── README.md
│
├── 📂 trpg-master-ai/            # Gemini AI 기반 인터랙티브 TRPG 마스터 (Next.js 16)
│   ├── data/                     # D&D 5e 기본 규칙 및 테마별 시나리오 텍스트
│   ├── public/                   # 판타지 맵 및 도면 이미지 에셋
│   ├── .env.example              # GEMINI_API_KEY 설정 템플릿
│   └── README.md
│
├── 📂 win-search-tool/           # 트레이 로컬 파일/내용 실시간 검색기 (Python)
│   ├── local_search_tray.py      # Tkinter GUI & Watchdog 파일시스템 감시
│   ├── research/                 # WSearch 서비스 및 COM 진단 스크립트 모음
│   └── README.md
│
└── 📂 virtual-monitor-tools/     # 가상 모니터 드라이버 진단 및 복구 스크립트
    ├── check_monitors.py         # 다중 모니터 해상도/좌표 진단
    ├── restore_monitor.py        # UAC 승격 가상 드라이버 복구
    └── README.md
```

---

## 🔒 보안 및 환경 변수 관리

- **API 키 및 시크릿 토큰 보호**: 
  - 실제 API 키(`Gemini API Key`, `Supabase Key` 등)가 저장된 `.env` 및 `.env.local` 파일은 루트 및 각 하위 프로젝트의 `.gitignore`에 의해 Git 추적 대상에서 **완벽히 차단**되어 있습니다.
- **환경 변수 세팅 방법**:
  - 각 웹 프로젝트 폴더에 진입하여 `.env.example` 파일을 복사해 `.env.local` (또는 `.env`)을 생성한 후 본인의 키를 입력하세요.
  ```bash
  cd trpg-master-ai
  cp .env.example .env.local
  # .env.local 파일을 열고 GEMINI_API_KEY 입력
  ```

---

## ⚡ 빠른 실행 가이드 (Quick Start)

### 1. Web 프로젝트 실행 (예: `trpg-master-ai`, `juje-web`, `broadcast-cg-fun`)
```bash
# 원하는 프로젝트 디렉토리로 이동
cd trpg-master-ai

# 의존성 설치
npm install

# 개발 서버 구동 (trpg: 62010 포트 / juje: 62020 포트 / broadcast: 3000 포트)
npm run dev
```

### 2. Python 데스크톱 도구 실행 (예: `discord-auto-mute`, `win-search-tool`)
```bash
# 원하는 도구 디렉토리로 이동
cd win-search-tool

# 의존성 설치
pip install -r requirements.txt

# 실행
python local_search_tray.py
```

---

## 📜 라이선스

This project is licensed under the MIT License.
