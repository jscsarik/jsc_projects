# 🎮 osu! Selective Downloader (오스! 비트맵 난이도별 선택 다운로더)

> **osu! 공식 웹사이트에서 플레이어가 원하는 특정 난이도(Diff)만 골라서 가볍게 다운로드하는 Chrome 확장 프로그램**  
> 불필요한 고난도/저난도 비트맵으로 인한 디스크 용량 낭비를 방지하고, 필요한 난이도 파일(`.osu`)과 음원만 추출하여 압축 다운로드합니다.

---

## 📌 주요 특징 (Key Features)

- 🎯 **선택적 비트맵 패키징 다운로드**
  - 전체 비트맵 팩을 통째로 받을 필요 없이, 내가 플레이하고 싶은 특정 난이도만 체크하여 다운로드
- 🌐 **Chrome 확장 프로그램 간편 설치 (Manifest V3)**
  - 최신 Manifest V3 표준 준수로 가볍고 안전하게 실행
  - osu! 비트맵 상세 페이지 방문 시 직관적인 팝업(`popup.html`) UI 자동 연동
- ⚡ **클라이언트 사이드 인메모리 압축 (`jszip`)**
  - 별도 서버 통신 없이 브라우저 내에서 `JSZip` 라이브러리로 직접 `.osz` 패키지를 조합하여 즉시 다운로드

---

## 🛠️ 기술 스택 (Tech Stack)

- **Platform**: Chrome Extension (Manifest V3)
- **Frontend**: HTML5, Vanilla JavaScript, CSS3
- **Libraries**: `jszip` (인메모리 압축), `matter-js`
- **Build Tools**: Vite, TypeScript

---

## 🚀 빠른 시작 (Getting Started)

### 1. 확장 프로그램 Chrome에 등록하기
1. Google Chrome 브라우저를 실행하고 주소창에 `chrome://extensions/`를 입력합니다.
2. 우측 상단의 **[개발자 모드]** 스위치를 켭니다.
3. 좌측 상단에 나타난 **[압축해제된 확장 프로그램을 로드합니다]** 버튼을 클릭합니다.
4. 본 프로젝트 폴더(`osu-selective-downloader`)를 선택합니다.
5. 크롬 우측 상단 퍼즐 아이콘을 눌러 **osu! Selective Downloader**를 고정합니다.

### 2. 비트맵 다운로드 사용법
1. [osu! 공식 비트맵 웹사이트](https://osu.ppy.sh/beatmapsets)에 접속합니다.
2. 원하는 곡의 페이지에서 상단 확장 프로그램 아이콘을 클릭합니다.
3. 팝업에서 다운로드할 난이도를 체크한 뒤 다운로드 버튼을 누릅니다.

> [!TIP]  
> 다운로드된 `.osz` 파일을 더블 클릭하면 실행 중인 osu! 게임 클라이언트에 자동으로 비트맵이 설치됩니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── manifest.json            # 크롬 확장 프로그램 매니페스트 (V3)
├── background.js            # 서비스 워커 백그라운드 이벤트 리스너
├── content.js               # osu! 웹페이지 DOM 분석 및 다운로드 인터셉트
├── popup.html               # 확장 프로그램 팝업 인터페이스
├── popup.js                 # 난이도 체크박스 조작 및 다운로드 로직
├── libs/                    # jszip 등 클라이언트 라이브러리
├── icons/                   # 확장 프로그램 해상도별 아이콘 (16, 48, 128)
├── capture*.png             # 사용법 안내 캡처 이미지
└── README.md
```
