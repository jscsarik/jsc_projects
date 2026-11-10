# 🎯 JUJE Web (실시간 주제어 추리 파티 게임 웹 플랫폼)

> **친구들과 함께 실시간으로 즐기는 '주제어' 추리 및 라이어 파티 게임 웹 클라이언트**  
> Supabase Realtime을 기반으로 방 생성, 참여, 실시간 역할 배정, 라운드 진행, 타이머 동기화, 배경음악 연출을 제공합니다.

---

## 📌 주요 기능

- 🕹️ **실시간 룸 및 동기화 게임 플레이**
  - 방 생성 및 코드 입장을 통한 다자간 멀티플레이 지원
  - 참가자 상태, 투표, 라운드 진행 상황이 밀리초 단위로 전체 참가자에게 실시간 반영
- 🎭 **다채로운 게임 모드 및 테마**
  - 라이어 게임 모드, 탐정 추리 모드, 시크릿 소설 테마 등 다양한 장르의 주제어 풀 지원
- ⏱️ **동기화 타이머 & 긴장감 넘치는 사운드 연출**
  - 서버 시간 기준 타이머 동기화로 부정행위 방지
  - 게임 상황(시작, 투표, 판결, 결과)에 맞춘 BGM 및 사운드 이펙트 자동 재생
- 📱 **모바일 & 데스크톱 반응형 UI**
  - TailwindCSS v4 및 Lucide 아이콘을 활용한 세련된 글래스모피즘(Glassmorphism) 다크 모드 UI

---

## 🛠️ 기술 스택

- **Framework**: [Next.js 16 (App Router)](https://nextjs.org/)
- **Frontend**: React 19, TypeScript, Tailwind CSS v4, Lucide React
- **Backend / Realtime Database**: [Supabase](https://supabase.com/)
- **State Management**: React Hooks & Realtime Broadcast

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
`.env.example`을 복사하여 `.env.local`을 생성하고 Supabase 프로젝트 정보를 입력합니다.
```bash
cp .env.example .env.local
```

`.env.local` 내용:
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-public-key-here
```

### 4. 로컬 개발 서버 실행
기본 개발 포트는 `62020`으로 지정되어 있습니다.
```bash
npm run dev
```
브라우저에서 `http://localhost:62020`으로 접속합니다.

---

## 📂 프로젝트 구조

```text
├── app/
│   ├── layout.tsx          # 루트 레이아웃 및 폰트/스타일 설정
│   ├── page.tsx            # 메인 게임 로비, 방 생성 및 플레이 화면 (단일 페이지 풀스택 구현)
│   └── globals.css         # TailwindCSS v4 디자인 시스템 설정
├── bgm/                    # 상황별 게임 사운드 및 BGM 리소스
├── lib/                    # Supabase 클라이언트 및 게임 헬퍼 로직
├── public/                 # 파비콘 및 정적 그래픽 에셋
├── .env.example            # 환경변수 템플릿
├── next.config.ts          # Next.js 설정
└── package.json
```
