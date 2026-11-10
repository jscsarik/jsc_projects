# 🎮 osu! Selective Downloader (오스! 비트맵 난이도별 선택 다운로더)

> **osu! 웹사이트에서 원하는 난이도(Diff)만 골라서 가볍게 다운로드할 수 있는 Chrome 확장 프로그램**  
> 불필요한 고난도/저난도 비트맵으로 인한 디스크 낭비를 줄이고, 플레이어가 원하는 난이도만 선택적으로 추출 및 다운로드합니다.

---

## 📌 주요 기능

- 🎯 **선택적 비트맵 다운로드**
  - 전체 비트맵 팩을 통째로 받을 필요 없이, 내가 플레이하고 싶은 특정 난이도만 필터링하여 다운로드
- 🌐 **Chrome 확장 프로그램 간편 설치**
  - 설치 후 osu! 비트맵 상세 페이지 방문 시 직관적인 팝업(`popup.html`) UI 자동 연동
- ⚡ **빠른 다운로드 & 경량 번들링**
  - 가벼운 백그라운드 서비스 워커(`background.js`) 및 콘텐츠 스크립트(`content.js`) 구조

---

## 🛠️ 기술 스택

- **Platform**: Chrome Extension (Manifest V3)
- **Frontend**: HTML5, Vanilla JavaScript, CSS3
- **Tools**: Vite, TypeScript

---

## 🚀 Chrome에 설치 및 사용 방법

### 1. 확장 프로그램 로드하기
1. Google Chrome 브라우저를 실행하고 주소창에 `chrome://extensions/`를 입력합니다.
2. 우측 상단의 **[개발자 모드]** 스위치를 켭니다.
3. 좌측 상단에 나타난 **[압축해제된 확장 프로그램을 로드합니다]** 버튼을 클릭합니다.
4. 본 프로젝트 폴더(`osu-selective-downloader`)를 선택합니다.
5. 크롬 우측 상단 퍼즐 아이콘을 눌러 **osu! Selective Downloader**를 고정합니다.

### 2. 비트맵 다운로드 사용법
1. [osu! 공식 비트맵 웹사이트](https://osu.ppy.sh/beatmapsets)에 접속합니다.
2. 원하는 곡의 페이지에서 확장 프로그램 아이콘을 클릭합니다.
3. 다운로드할 난이도를 체크한 뒤 다운로드 버튼을 누릅니다.

---

## 📂 프로젝트 구조

```text
├── manifest.json              # 크롬 확장 프로그램 매니페스트 (V3)
├── background.js              # 백그라운드 이벤트 리스너
├── content.js                 # osu! 웹페이지 DOM 파싱 및 다운로드 인터셉트
├── popup.html                 # 확장 프로그램 팝업 UI
├── popup.js                   # 팝업 조작 및 난이도 선택 로직
├── icons/                     # 확장 프로그램 아이콘
├── capture*.png               # 실행 화면 캡처 스크린샷
└── README.md
```
