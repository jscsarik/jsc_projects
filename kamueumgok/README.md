# 🎵 가무음곡 (KaMuEumGok / 歌舞音曲)

> **Next.js 16과 Electron을 결합한 차세대 로컬 데스크톱 오디오 & 뮤직 플레이어**  
> 감각적인 UI와 부드러운 애니메이션(`framer-motion`), 그리고 로컬 음원 메타데이터 실시간 파싱(`music-metadata`)을 통해 최상의 음악 감상 경험을 제공하는 네이티브 플레이어입니다.

---

## 📌 주요 특징 (Key Features)

- 🖥️ **Electron 기반 네이티브 데스크톱 플레이어**
  - 커스텀 스트리밍 프로토콜(`music-app://`)을 통한 대용량 고음질 무손실 음원 실시간 스트리밍
  - 앱 시작 시 커스텀 스플래시(Splash) 로고 화면 및 보더리스 윈도우 지원
- 📂 **로컬 디렉토리 재귀적 음원 스캐닝**
  - PC 내 지정 폴더의 오디오 파일(`mp3`, `flac`, `wav`, `m4a` 등)을 고속 탐색
  - `music-metadata` 라이브러리를 통해 앨범 아트워크, 아티스트, 앨범명, 트랙 정보 자동 추출
- 🎛️ **Next.js 16 + Framer Motion 인터페이스**
  - 재생 바, 가사 뷰, 플레이리스트 큐, 재생/일시정지/셔플 모드 애니메이션
- 🚀 **백그라운드 무음 런처 지원**
  - `KaMuEumGok.bat` 및 `Run_start.vbs`를 통한 터미널 창 없는 깔끔한 실행 지원

---

## 🛠️ 기술 스택 (Tech Stack)

- **Desktop Framework**: [Electron 40](https://www.electronjs.org/)
- **Web Framework**: [Next.js 16 (Turbopack)](https://nextjs.org/)
- **Frontend**: React 19, TypeScript, Tailwind CSS, Framer Motion, Lucide React
- **Audio Engine**: `music-metadata` (ID3v2, FLAC Vorbis 메타데이터 파싱)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 20.0 이상
- npm / yarn

### 2. 패키지 설치
```bash
npm install
```

### 3. 개발 모드 실행 (Next.js + Electron 동시 구동)
```bash
npm run electron:dev
```
Next.js 개발 서버가 실행된 뒤 자동으로 Electron 창이 연동되어 켜집니다.

### 4. 웹 모드만 단독 실행
```bash
npm run dev
```
브라우저에서 `http://localhost:3000`으로 접속합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── main.js                  # Electron 메인 프로세스 (프로토콜 등록, 윈도우 생성, 파일시스템 I/O)
├── preload.js               # Electron 렌더러 IPC 보안 브릿지
├── src/                     # Next.js 프론트엔드 (플레이어 UI, 애니메이션 컴포넌트)
├── KaMuEumGok.bat           # 윈도우 실행 배치 스크립트
├── Run_start.vbs            # 백그라운드 무음 실행 스크립트
├── icon.ico / icon.png      # 애플리케이션 아이콘
└── package.json
```
