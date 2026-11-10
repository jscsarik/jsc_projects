# 🎬 Broadcast CG Fun (실시간 방송 CG 오버레이 & 모바일 원격 제어 시스템)

> **OBS Studio 및 vMix 방송 송출 화면을 실시간으로 제어하는 차세대 방송 자막 및 전광판 웹 솔루션**  
> 스마트폰 리모컨(`/remote`)과 OBS 브라우저 소스(`/screen`)가 Supabase Realtime 초저지연 웹소켓을 통해 밀리초 단위로 양방향 동기화됩니다.

---

## 📌 주요 특징 (Key Features)

- 🖥️ **투명 배경 OBS 브라우저 오버레이 (`/screen`)**
  - 방송 송출 화면 위에 자연스럽게 얹어지는 무배경 고해상도 그래픽 오버레이
  - 실시간 자막, 알림 메시지 배너, 유튜브/동영상 팝업 재생(`react-player`) 지원
- 📱 **모바일 반응형 원격 제어 리모컨 (`/remote`)**
  - 스마트폰, 태블릿, 세컨드 모니터 어디서나 터치 한 번으로 즉시 자막 송출
  - 효과음 재생, 짤방/GIF 팝업 큐잉, 긴급 화면 클리어 등 연출자 전용 핫키 제공
- 🎙️ **실시간 음성 합성 TTS (Text-to-Speech) 연동 (`/api/tts`)**
  - 자막 텍스트 입력 시 서버 사이드에서 음성을 자동 합성하여 방송 화면에 오디오 동시 출력
- ⚡ **초저지연 WebSocket 실시간 동기화**
  - Supabase Realtime 채널을 기반으로 별도의 수동 새로고침 없이 즉각적인 화면 갱신 실현

---

## 🛠️ 기술 스택 (Tech Stack)

- **Framework**: [Next.js (App Router)](https://nextjs.org/)
- **Frontend**: React 19, Tailwind CSS
- **Backend & Realtime**: [Supabase](https://supabase.com/) (Realtime WebSockets & Database)
- **Media Player**: `react-player`
- **Deployment**: Vercel / Node.js

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 18.17 이상
- npm / yarn / pnpm
- Supabase 프로젝트 (무료 티어 지원)

### 2. 패키지 설치
```bash
npm install
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env.local`을 생성하고 Supabase 프로젝트 키를 입력합니다.
```bash
cp .env.example .env.local
```

`.env.local` 내용:
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-public-key-here
```

### 4. 로컬 개발 서버 실행
```bash
npm run dev
```
브라우저에서 `http://localhost:3000`으로 접속합니다.

---

## 🎥 OBS 스튜디오 연동 가이드 (OBS Integration Guide)

1. OBS Studio를 실행하고 **[소스 목록]**에서 `+` 버튼 클릭 후 **[브라우저(Browser)]** 소스를 추가합니다.
2. **URL** 항목에 `http://localhost:3000/screen` (또는 Vercel 배포 URL/screen)을 입력합니다.
3. 너비 `1920`, 높이 `1080` (방송 송출 해상도)을 지정합니다.
4. 스마트폰이나 보조 모니터 브라우저에서 `http://localhost:3000/remote`에 접속하여 실시간으로 CG 자막과 미디어를 제어합니다.

> [!TIP]  
> OBS 브라우저 소스 속성에서 **'OBS를 통해 오디오 제어'**를 체크하면, 자막 효과음 및 TTS 음량을 OBS 오디오 믹서에서 자유롭게 조절할 수 있습니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── app/
│   ├── api/tts/route.js     # TTS 음성 합성 서버리스 API 엔드포인트
│   ├── remote/page.js       # 연출/스태프용 실시간 모바일 리모컨 UI
│   ├── screen/page.js       # OBS 송출용 브라우저 오버레이 자막/미디어 뷰
│   ├── layout.js            # 루트 레이아웃
│   └── page.js              # 홈 화면 (경로 선택 및 OBS 설정 가이드)
├── lib/                     # Supabase 클라이언트 초기화 및 유틸 함수
├── public/                  # 정적 리소스 (효과음, 안내 아이콘 등)
├── .env.example             # 환경변수 템플릿
├── vercel.json              # Vercel 배포 구성 파일
└── package.json
```
