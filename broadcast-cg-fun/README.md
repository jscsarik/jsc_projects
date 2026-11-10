# 🎬 Broadcast CG Fun (실시간 방송 CG 오버레이 & 원격 제어 시스템)

> **OBS / vMix 방송 송출 화면을 실시간으로 제어할 수 있는 차세대 방송 자막 및 전광판 웹 솔루션**  
> 모바일 리모컨(`/remote`)과 OBS 브라우저 소스(`/screen`)가 Supabase Realtime을 통해 딜레이 없이 실시간 동기화됩니다.

---

## 📌 주요 기능

- 🖥️ **OBS 오버레이 전광판 (`/screen`)**
  - 투명 배경의 깔끔한 방송용 오버레이 화면 지원
  - 실시간 자막, 알림 메시지, 유튜브/비디오 영상 팝업 재생(`react-player`)
  - 애니메이션 트랜지션 및 시각 효과 내장
- 📱 **모바일 & PC 원격 제어 리모컨 (`/remote`)**
  - 스마트폰, 태블릿, 세컨드 모니터에서 직관적으로 터치 조작 가능한 UI
  - 자막 텍스트 즉시 송출, 알림 사운드, 영상 큐잉, 화면 초기화 기능
- 🎙️ **실시간 TTS(Text-to-Speech) 음성 송출 (`/api/tts`)**
  - 텍스트 입력 시 서버 사이드 음성 합성 후 방송 화면에 실시간 음성 및 자막 동시 출력
- ⚡ **초저지연 실시간 동기화**
  - Supabase Realtime 채널을 통한 WebSocket 통신으로 밀리초 단위 즉시 반응

---

## 🛠️ 기술 스택

- **Framework**: [Next.js (App Router)](https://nextjs.org/)
- **Frontend**: React 19, Tailwind CSS
- **Backend / Realtime**: [Supabase](https://supabase.com/) (Realtime WebSockets & Database)
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

## 🎥 OBS 스튜디오 연동 가이드

1. OBS Studio를 실행하고 **소스 목록**에서 `+` 버튼 클릭 후 **브라우저(Browser)** 소스를 추가합니다.
2. **URL** 항목에 `http://localhost:3000/screen` (또는 Vercel 배포 URL/screen)을 입력합니다.
3. 너비 `1920`, 높이 `1080` (방송 해상도에 맞춤)을 설정합니다.
4. 스마트폰이나 서브 브라우저로 `http://localhost:3000/remote`에 접속하여 실시간으로 CG 자막과 미디어를 컨트롤합니다.

---

## 📂 프로젝트 구조

```text
├── app/
│   ├── api/tts/route.js    # TTS 음성 합성 API 엔드포인트
│   ├── remote/page.js      # 연출/스태프용 모바일 리모컨 페이지
│   ├── screen/page.js      # OBS 송출용 브라우저 오버레이 페이지
│   ├── layout.js           # 루트 레이아웃
│   └── page.js             # 홈 (경로 선택 및 가이드 화면)
├── lib/                    # Supabase 클라이언트 및 유틸 함수
├── public/                 # 정적 리소스 (이미지, 효과음 등)
├── .env.example            # 환경변수 예시 파일
└── package.json
```
