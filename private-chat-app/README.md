# 🔒 Private Chat App (보안 실시간 채팅 웹 애플리케이션)

> **Vite + React 19와 Supabase Realtime으로 구축된 초경량 고속 프라이빗 채팅 웹 애플리케이션**  
> 비밀스러운 대화, 초저지연 실시간 메시징, 오디오 사운드 알림을 제공하며 불필요한 흔적을 남기지 않는 안전한 소통 공간을 제공합니다.

---

## 📌 주요 특징 (Key Features)

- 🔐 **초간단 인증 & 익명 입장 (Auth)**
  - 복잡한 가입 절차 없이 안전하게 로그인하고 대화에 참여할 수 있는 간결한 인증 시스템
- 💬 **초저지연 실시간 메시징 (Realtime Chat)**
  - Supabase WebSocket 채널을 통해 새로고침 없이 즉시 전송되는 실시간 채팅
  - 메시지 수신 시 부드러운 스크롤 애니메이션 및 가독성 높은 버블 UI
- 🔔 **스마트 오디오 매니저 (`audioManager.ts`)**
  - 메시지 송수신 상황에 맞춘 인터랙티브 효과음 지원
- ⚡ **초고속 Vite 번들링 & Oxlint 적용**
  - 최신 Vite 빌드 환경과 Rust 기반 고속 린터 Oxlint로 쾌적한 개발 및 빌드 환경 제공

---

## 🛠️ 기술 스택 (Tech Stack)

- **Build Tool**: [Vite](https://vitejs.dev/)
- **Frontend**: React 19, TypeScript
- **Backend & BaaS**: [Supabase](https://supabase.com/) (Auth & Realtime)
- **Linter**: Oxlint
- **Deployment**: Vercel / Cloudflare Pages / Static Hosting

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 18.0 이상
- npm / yarn / pnpm

### 2. 패키지 설치
```bash
npm install
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 Supabase 프로젝트 설정을 입력합니다.
```bash
cp .env.example .env
```

`.env` 내용:
```env
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-public-key-here
```

### 4. 로컬 개발 서버 실행
```bash
npm run dev
```
브라우저에서 `http://localhost:5173`으로 접속합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── src/
│   ├── assets/              # 로고, 히어로 배너 및 벡터 그래픽
│   ├── components/
│   │   ├── Auth.tsx         # 로그인 및 인증 처리 컴포넌트
│   │   └── Chat.tsx         # 실시간 메시지 송수신 및 대화창 UI
│   ├── lib/
│   │   ├── audioManager.ts  # 사운드 알림 및 오디오 제어 모듈
│   │   └── supabaseClient.ts # Supabase 클라이언트 인스턴스 초기화
│   ├── App.tsx              # 앱 루트 컴포넌트 (상태 및 뷰 전환 관리)
│   ├── main.tsx             # React DOM 렌더링 엔트리포인트
│   └── index.css            # 전역 스타일시트
├── index.html               # HTML 템플릿
├── .env.example             # 환경변수 템플릿
├── vite.config.ts           # Vite 설정 파일
└── package.json
```
