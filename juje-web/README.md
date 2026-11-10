# 🎯 JUJE Web (실시간 주제어 추리 파티 게임 웹 플랫폼)

> **친구들과 함께 실시간으로 웹 브라우저에서 즐기는 '주제어' 추리 및 라이어 파티 게임 클라이언트**  
> Supabase Realtime 웹소켓 통신을 기반으로 방 생성, 입장, 실시간 역할 배정, 턴제 라운드 진행, 동기화 타이머 및 긴장감 넘치는 사운드 연출을 지원합니다.

---

## 📌 주요 특징 (Key Features)

- 🕹️ **실시간 룸 및 다자간 동기화 플레이**
  - 방 코드 생성을 통한 간편한 멀티플레이어 로비 입장
  - 참가자 레디 상태, 투표 현황, 라운드 전환이 전체 플레이어 화면에 실시간 동기화
- 🎭 **다채로운 추리 게임 모드 & 테마 카테고리**
  - 라이어 게임 모드, 탐정 모드, 비밀 소설 테마 등 다양한 고유 주제어 데이터 풀 내장
- ⏱️ **서버 기준 동기화 타이머 & 사운드 이펙트**
  - 서버 시계 기반의 정확한 카운트다운 타이머로 라운드 시간 초과 판정
  - 게임 상황(시작, 투표, 판결, 결과)에 맞춘 긴장감 넘치는 BGM 및 SFX 자동 재생
- 📱 **모바일 & 데스크톱 반응형 다크 테마 UI**
  - TailwindCSS v4와 Lucide React 기반의 세련된 글래스모피즘(Glassmorphism) 다크 모드

---

## 🛠️ 기술 스택 (Tech Stack)

- **Framework**: [Next.js 16 (App Router)](https://nextjs.org/)
- **Frontend**: React 19, TypeScript, Tailwind CSS v4, Lucide React
- **Backend & Database**: [Supabase](https://supabase.com/) (Realtime WebSockets & Database)
- **Audio**: HTML5 Web Audio API (`bgm/`)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 20.0 이상
- npm / yarn / pnpm

### 2. 패키지 설치
```bash
npm install
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env.local`을 생성하고 Supabase 프로젝트 설정을 입력합니다.
```bash
cp .env.example .env.local
```

`.env.local` 내용:
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-public-key-here
```

### 4. 로컬 개발 서버 실행
본 프로젝트의 기본 포트는 **`62020`**으로 지정되어 있습니다.
```bash
npm run dev
```
브라우저에서 `http://localhost:62020`으로 접속합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── app/
│   ├── layout.tsx           # 전역 폰트 및 다크 테마 레이아웃
│   ├── page.tsx             # 로비, 대기실, 인게임 풀스택 단일 페이지 UI
│   └── globals.css          # TailwindCSS v4 디자인 시스템
├── bgm/                     # 게임 상황별 BGM 및 효과음 오디오 리소스
├── lib/
│   ├── supabase.ts          # Supabase Realtime 클라이언트 인스턴스
│   └── words.ts             # 카테고리별 주제어/라이어 단어 데이터베이스
├── public/                  # 정적 그래픽 에셋
├── .env.example             # 환경변수 템플릿
├── next.config.ts           # Next.js 설정
└── package.json
```
