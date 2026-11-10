# 👑 IDOL Manager (아이돌 기획사 육성 경영 시뮬레이션 게임)

> **Python과 SQLite 기반으로 구축된 풀스케일 K-POP 엔터테인먼트 기획사 경영 시뮬레이터**  
> 🌐 **공식 위키 / 데이터베이스 (Vercel):** [https://idol-manager-wiki.vercel.app/](https://idol-manager-wiki.vercel.app/)  
> 연습생 스카우트, 맞춤형 트레이닝, 정규 리그 대결, 앨범 발매, 재무 및 급여 정산까지 기획사 대표로서의 모든 의사결정을 실시간 시뮬레이션 엔진으로 경험할 수 있는 데스크톱 게임입니다.

---

## 📌 주요 특징 (Key Features)

- 🎤 **체계적인 육성 및 트레이닝 시스템**
  - 보컬, 댄스, 비주얼, 예능감 등 다면적 능력치 모델링 및 피로도/부상 메커니즘
  - 1군 / 2군 로스터 분리 운영, 개인별 포지션 배정 및 주간 성장/노화 라이프사이클 반영
- 🏆 **정규 시즌 및 포스트시즌 리그전 (217일 대서사)**
  - 24주 정규 리그 + 3주 포스트시즌 + 4주 비시즌으로 구성된 31주 풀 캘린더
  - 타 기획사와의 주간 매치업 대결, 실시간 판정 엔진 및 하이라이트 중계 UI
- 💰 **정밀한 기획사 재무 및 계약 관리 (Finance Engine)**
  - 앨범 판매, 공연 수익, 고정 운영비 및 4주 주기 급여 정산
  - FA(자유계약선수) 시장, 타 기획사와의 트레이드 협상 및 스폰서십 체결
- 🎵 **풍부한 인터랙티브 멀티미디어 에셋**
  - 실제 K-POP 음원 기반의 상황별 동적 BGM 재생 (평시 로비, 긴장감 넘치는 배틀 씬)
  - 600여 종 이상의 고화질 아이돌 일러스트 및 기획사 로고 시스템 내장
- 🖥️ **직관적인 데스크톱 GUI & 원클릭 실행**
  - Tkinter/PyQt 기반 글래스 스타일 테마, 패널 도킹 및 창 크기 자동 비율 조정
  - 배치 파일(`실행하기.bat`) 또는 바로가기(`start.lnk`)를 통한 손쉬운 무설치 실행

---

## 🛠️ 기술 스택 (Tech Stack)

- **Language**: Python 3.10+
- **GUI Framework**: Tkinter / PySide (Custom Themed UI)
- **Database**: SQLite3 (ACID 트랜잭션 및 자동 백업 체계)
- **Audio Engine**: `pygame.mixer` (동적 BGM 재생 및 볼륨 컨트롤)
- **Packaging & Build**: PyInstaller, VBScript Launcher
- **Testing**: `pytest`, `unittest` (600여 개 이상의 통합 및 단위 테스트 슈트)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Windows 10 / 11 64-bit
- Python 3.10 이상 (소스코드 구동 시)

### 2. 필수 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 3. 게임 실행하기

#### 방법 A. 배치 파일로 즉시 실행 (가장 추천)
폴더 내의 **`실행하기.bat`** 또는 **`start.bat`** 파일을 더블 클릭하면 자동으로 환경을 확인하고 게임이 시작됩니다.

#### 방법 B. 터미널에서 직접 실행
```bash
python main.py
```

> [!TIP]  
> - 게임 데이터는 `data/` 및 사용자 로컬 저장소(`%LOCALAPPDATA%\IDOL_Manager\saves\`)에 SQLite DB 형태로 안전하게 자동 저장됩니다.  
> - BGM 음량이나 세부 화면 배치는 게임 내 설정 메뉴 또는 `config/` JSON 파일에서 조절할 수 있습니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── idol_manager/            # 게임 코어 로직 패키지
│   ├── core/                # 시뮬레이션 루프, 경기 엔진, 스케줄러
│   ├── models/              # 아이돌, 기획사, 경기, 재무 데이터 모델
│   ├── ui/                  # 메인 윈도우, 대진표, 트레이닝 룸, 기록실 UI
│   └── audio/               # BGM 및 효과음 재생 컨트롤러
├── assets/                  # 멀티미디어 에셋 라이브러리
│   ├── audio/               # 상황별 K-POP BGM 음원 (default / battle)
│   ├── idols/               # 아이돌 캐릭터 고화질 일러스트
│   ├── agencies/            # 기획사 공식 로고 이미지
│   └── title/               # 타이틀 및 인게임 그래픽 리소스
├── config/                  # 신인 드래프트, 재무, 밸런스 설정 JSON
├── docs/                    # 1차~29차 시스템 상세 기획서 및 패치노트 아카이브
├── tests/                   # 600여 개의 단위 테스트 및 밸런스 시뮬레이션 검증 코드
├── tools/                   # 데이터베이스 마이그레이션 및 릴리즈 빌드 자동화 스크립트
├── requirements.txt         # 실행 의존성 목록
├── IDOL_Manager.spec        # PyInstaller 단일 실행파일 빌드 스펙
├── main.py                  # 게임 애플리케이션 진입점 (Entry Point)
└── 실행하기.bat              # 원클릭 자동 실행 런처
```
