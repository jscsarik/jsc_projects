# 🖥️ Virtual Monitor Tools (가상 모니터 드라이버 진단 및 복구 도구)

> **Windows 가상 디스플레이(Virtual Display Driver / IddCx VDD)의 상태를 실시간 진단하고, 드라이버를 원클릭으로 설치 및 복구하는 시스템 유틸리티 모음**  
> 다중 모니터 환경에서 가상 디스플레이가 비활성화되거나 인식되지 않을 때 UAC 관리자 권한을 자동으로 획득하여 신속히 활성화합니다.

---

## 📌 주요 도구 목록

| 스크립트 파일 | 언어 | 설명 | 실행 권한 |
| :--- | :--- | :--- | :--- |
| **`check_monitors.py`** | Python | `mss` 라이브러리를 통해 현재 시스템에 연결된 전체 모니터의 해상도, 좌표, 개수 및 가상 모니터(Index 3) 인식 여부를 진단 | 일반 사용자 |
| **`restore_monitor.py`** | Python | 관리자 권한(UAC)을 자동 요청하고, `deviceinstaller64.exe enablevdd`를 실행하여 꺼진 가상 모니터를 즉시 복구 | 관리자 권한 필요 (자동 승격) |
| **`restore_monitor.ps1`** | PowerShell | PowerShell 환경에서 가상 디스플레이 디바이스를 초기화 및 재기동하는 복구 스크립트 | 관리자 권한 필요 |
| **`install_driver.ps1`** | PowerShell | 가상 디스플레이 드라이버(VDD) INF 등록 및 장치 설치를 자동화하는 파워쉘 스크립트 | 관리자 권한 필요 |

---

## 🚀 사용 방법

### 1. 모니터 상태 진단
```bash
pip install mss
python check_monitors.py
```
출력 예시:
```text
Platform: Windows 10
Monitors: 3
Monitor 0: {'left': 0, 'top': 0, 'width': 3840, 'height': 2160}
...
RESULT: Virtual Monitor Index 3 Found!
```

### 2. 가상 모니터 즉시 복구
가상 모니터가 연결 해제되었거나 감지되지 않을 때 실행:
```bash
python restore_monitor.py
```
> [!NOTE]  
> 실행 시 관리자 권한(UAC) 팝업이 뜨면 '예'를 눌러 복구를 진행합니다.

---

## 📂 파일 구성

```text
├── check_monitors.py        # 다중 모니터 실시간 인식 상태 진단
├── restore_monitor.py       # UAC 승격 및 enablevdd 실행 복구기
├── restore_monitor.ps1      # PowerShell 가상 모니터 복구 스크립트
├── install_driver.ps1       # PowerShell 드라이버 신규 설치 스크립트
└── .gitignore
```
