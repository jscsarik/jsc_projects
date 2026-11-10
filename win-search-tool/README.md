# 🔍 Windows Search Tray Tool (시스템 트레이 로컬 파일 실시간 검색기)

> **Windows 시스템 트레이에 상주하며 로컬 디스크의 파일명 및 텍스트 내용을 실시간으로 인덱싱하고 초고속으로 검색하는 데스크톱 유틸리티**  
> `watchdog` 기반의 실시간 파일시스템 변경 감지와 자동 인코딩 감지(`chardet`)를 통해 가볍고 빠른 검색 환경을 제공합니다.

---

## 📌 주요 기능

- 🗂️ **실시간 파일시스템 감시 (`watchdog`)**
  - 지정된 디렉토리의 파일 생성, 수정, 삭제 이벤트를 백그라운드 스레드에서 실시간 포착 및 인덱스 갱신
- 📝 **문서 본문 텍스트 실시간 검색**
  - 파일 이름뿐만 아니라 문서 파일(`txt`, `md`, `log`, `csv` 등)의 내부 텍스트 내용까지 실시간 탐색
  - `chardet` 라이브러리를 통해 UTF-8, CP949/EUC-KR 등 다양한 인코딩을 자동 판별하여 한글 깨짐 방지
- 💻 **시스템 트레이 상주 & 핫키 지원**
  - 트레이 아이콘 최소화 기능으로 시스템 리소스 최소 점유
  - 작업 표시줄 방해 없이 언제든 필요할 때 팝업하여 즉시 검색
- 📦 **단일 독립 실행 파일(.exe) 빌드 지원**
  - Python이 설치되지 않은 PC에서도 바로 실행할 수 있도록 `build_exe.bat` 원클릭 PyInstaller 빌드 스크립트 제공

---

## 🛠️ 기술 스택

- **Language**: Python 3.10+
- **GUI Framework**: Tkinter / ttk
- **Filesystem Monitoring**: `watchdog`
- **Text & Encoding**: `chardet`
- **Image Processing**: `Pillow` (PIL)
- **Packaging**: PyInstaller

---

## 🚀 빠른 시작 (Getting Started)

### 1. 의존성 패키지 설치
폴더 내의 `install_dependencies.bat`을 실행하거나 명령 프롬프트에서 아래 명령어를 입력합니다:
```bash
pip install -r requirements.txt
```
또는:
```bash
pip install watchdog chardet pillow
```

### 2. 프로그램 실행 (Python)
```bash
python local_search_tray.py
```

### 3. 독립 실행파일(.exe) 빌드
독립 실행 가능한 단일 파일로 배포하려면:
```bash
build_exe.bat
```
빌드가 완료되면 `dist/local_search_tray.exe` 파일이 생성됩니다.

---

## 🔬 연구 및 진단 스크립트 (`research/`)

`research/` 폴더에는 개발 과정에서 Windows Search 서비스 및 COM 인터페이스, 레지스트리 설정을 분석하기 위해 작성된 유틸리티가 보관되어 있습니다:

- `check_search_service.py`: Windows Search(`WSearch`) 서비스 상태 및 가동 여부 점검
- `check_search_reg.py`: Windows Search 레지스트리 설정 트리 구조 조회
- `check_search_roots.py`: Windows Search 인덱서의 기본 크롤링 루트 경로 조회
- `check_working_set.py`: 프로세스 메모리 워킹 셋(Working Set) 점유율 측정
- `test_com.py`: Windows Desktop Search COM 인터페이스(`ISearchManager`) 호출 테스트
- `test_ps_com.py`: PowerShell 기반 COM 객체 연동 테스트

---

## 📂 프로젝트 구조

```text
├── local_search_tray.py       # 트레이 상주 검색기 메인 프로그램
├── local_search_tray.spec     # PyInstaller 빌드 구성 파일
├── build_exe.bat              # PyInstaller 자동 빌드 배치 파일
├── install_dependencies.bat   # 필수 패키지 자동 설치 배치 파일
├── requirements.txt           # 의존성 패키지 목록
├── app_icon.ico               # 애플리케이션 및 트레이 아이콘
├── research/                  # Windows Search COM / 레지스트리 진단 스크립트
└── .gitignore                 # 빌드 및 캐시 폴더 제외
```
