# 📡 24h Auto Broadcaster (메타데이터 기반 24시간 무인 자동 송출 관제 시스템)

> **동아방송예술대학교 방송기술과 캡스톤디자인 졸업작품 (APC Prototype)**  
> 고가의 하드웨어 방송 스위처 없이 PC 1대와 OBS Studio WebSocket을 연동하여 24시간 무인/무중단으로 방송 영상을 자동 편성·송출하는 마스터 컨트롤 시스템입니다.

---

## 📌 주요 특징 (Key Features)

- 🔄 **무중단 핫스왑 (Zero-Downtime Hot-Swapping)**
  - 송출 중인 상황에서도 영상 라이브러리 폴더에 실시간으로 파일을 추가하거나 삭제할 수 있습니다.
  - 시스템 재부팅이나 스트림 중단 없이, 다음 큐시트 생성 주기 시 파일시스템 변경을 자동 감지하여 즉시 반영합니다.
- 🔀 **A/B Roll 핑퐁 스위칭 (블랙아웃 방지)**
  - 단일 미디어 소스를 사용할 때 발생하는 디코더 딜레이(검은 화면 깜빡임 현상)를 완벽히 해결했습니다.
  - OBS 상의 두 개 플레이어(`Player_1`, `Player_2`)를 번갈아 교차 제어하며, 0.15초 사전 버퍼링 기법을 적용하여 끊김 없는 심리스(Seamless) 트랜지션을 실현합니다.
- ⏱️ **정밀 러닝타임 자동 계산 (OpenCV)**
  - 비디오 파일(`mp4`, `mkv`, `mov` 등)의 총 프레임 수와 FPS를 `OpenCV`로 정밀 분석하여 밀리초(ms) 단위의 실제 재생 길이를 산출하고 타이머를 동기화합니다.
- 📋 **방송 4대 모듈 아키텍처 (CMS / DPC / CDS / APC)**
  1. **CMS (Content Management System)**: 영상 폴더 에셋 스캔 및 메타데이터 자동 추출
  2. **DPC (Dynamic Playlist Controller)**: 방송 편성 룰에 따른 실시간 동적 큐시트 생성
  3. **CDS (Content Delivery System)**: OBS WebSocket API를 통한 원격 제어
  4. **APC (Automatic Program Control)**: 전체 송출 라이프사이클을 관제하는 메인 마스터 엔진

---

## 🛠️ 기술 스택 (Tech Stack)

- **Language**: Python 3.10+
- **Broadcasting Engine**: OBS Studio (v28+ WebSocket 지원)
- **WebSocket Client**: `obsws-python`
- **Video Analysis**: `opencv-python` (OpenCV)
- **Architecture**: Dual Player (A/B Roll) Seamless Switching

---

## 🎥 시스템 구조 및 시연

<div align="center">
  <img width="400" height="260" alt="Architecture" src="https://github.com/user-attachments/assets/f7b1bb6d-e97f-46ac-ac4e-2b14a28f0e70" />
  <img width="400" height="260" alt="Workflow" src="https://github.com/user-attachments/assets/1944eb8d-e679-4a37-91e4-076b36ae9272" />
  <img width="380" height="230" alt="UI Diagram" src="https://github.com/user-attachments/assets/db4c1b57-500f-4a3c-b792-ec5deba9c61f" />
</div>

<div align="center">
  <img width="540" height="288" alt="Switching Demo" src="https://github.com/user-attachments/assets/6d96ea53-c34f-4735-9f92-837639e79266" />
</div>

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Python 3.10 이상
- OBS Studio v28 이상

### 2. 필수 라이브러리 설치
```bash
pip install -r requirements.txt
# 또는
pip install obsws-python opencv-python
```

### 3. OBS Studio 설정
1. OBS Studio 실행 후 상단 메뉴의 **[도구] ➔ [WebSocket 서버 설정]**을 클릭합니다.
2. **'WebSocket 서버 활성화'**를 체크합니다 (기본 서버 포트: `6161`).
3. 비밀번호를 설정했다면 `apc_main.py`의 `OBS_CONFIG['password']`에 입력합니다.
4. 대상 장면(기본 `'장면 3'`)에 **미디어 소스 2개**를 생성하고, 이름을 각각 **`Player_1`**, **`Player_2`**로 지정합니다.

### 4. 프로그램 실행
```bash
python apc_main.py
```
> [!NOTE]  
> OBS가 켜져 있지 않아도 테스트를 위해 가상 시뮬레이션 모드로 자동 폴백(Fallback)되어 로직을 검증할 수 있습니다.

---

## 📂 프로젝트 구조

```text
├── apc_main.py              # CMS, DPC, CDS, APC 통합 메인 송출 관제 엔진
├── drawing.pdf              # 시스템 계통도 및 시퀀스 설계 도면
├── requirements.txt         # 필수 파이썬 패키지 목록
├── source                   # 샘플 영상 소스 및 방송 레퍼런스 메타 정보
├── LICENSE                  # 라이선스
└── README.md
```
