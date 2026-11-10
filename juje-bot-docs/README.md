<div align="center">
  <img width="1200" height="475" alt="GHBanner" src="https://ai.google.dev/static/site-assets/images/share-ais-513315318.png" />
</div>

# 📖 JuJebot Docs (주제어 봇 게임 룰북 & 설명서 웹)

> **주제어BOT 미니게임 9종의 공식 규칙과 플레이 가이드를 제공하는 반응형 다크모드 웹 애플리케이션**  
> 🌐 **Vercel 배포 URL:** [https://juje-bot.vercel.app/](https://juje-bot.vercel.app/)  
> 디스코드 테마 스타일의 직관적인 사이드바 내비게이션을 통해 서바이벌, 3라운드 라이어, 바보 라이어, 텔레파시, 제로섬 데스매치, 칼전, 비밀소설 추리, 영웅시장, 지하철 서바이벌의 상세 룰을 한눈에 확인할 수 있습니다.

---

## 📌 주요 특징 (Key Features)

- 🎮 **주제어BOT 9개 미니게임 공식 룰북 탑재**
  - **주제어 서바이벌**: 기본 7초, 15턴 이후 5초 폭주 피지컬 단어 릴레이
  - **3라운드 라이어**: 3라운드 누적 승점제, 발언/지목/처형 및 라이어 역전 정답 찬스
  - **바보 라이어**: 모두가 단어를 받지만 1명만 다른 단어를 받는 블라인드 마피아
  - **텔레파시**: 주인공의 선택을 예측하여 살아남는 눈치 서바이벌
  - **제로섬 데스매치 / 칼전**: 상성과 체력 배분을 이용한 심리전
  - **비밀소설 추리 / 영웅시장 / 지하철 서바이벌**: 특수 룰셋 및 맵 기반 게임 가이드
- 🎨 **디스코드 감성 다크모드 UI (Discord-inspired Theme)**
  - Discord 특유의 다크 배경 컬러(`bg-[#36393f]`, `#2f3136`)와 Blurple(`text-[#5865F2]`) 포인트를 적용하여 음성 통화 중에도 편안하게 열람 가능합니다.
- 📱 **완벽한 반응형 모바일 지원 & 애니메이션 (Motion)**
  - 모바일 화면에서는 햄버거 메뉴 토글 사이드바가 지원되며, 게임 선택 시 최상단 자동 스크롤 및 부드러운 화면 전환을 제공합니다.
- 📝 **풍부한 마크다운 & HTML 렌더링**
  - `react-markdown` 및 `rehype-raw` 파서를 통해 강조 문구, 이모지, 팁 박스 등의 서식을 깔끔하게 렌더링합니다.
- ⚡ **Vercel 클라우드 최적화 배포**
  - 정적 SPA 빌드 구조로 Vercel 및 정적 웹 호스팅 환경에 초고속 배포가 가능합니다.

---

## 🛠️ 기술 스택 (Tech Stack)

- **Frontend**: React 19 (`react`, `react-dom`)
- **Build Tool**: Vite 6.2+
- **Styling**: Tailwind CSS v4 (`@tailwindcss/vite`, `tailwindcss`)
- **Animation**: Motion (`motion/react`)
- **Icons**: Lucide React (`lucide-react`)
- **Markdown Parser**: `react-markdown`, `rehype-raw`
- **Hosting / Deployment**: Vercel (`https://juje-bot.vercel.app/`)
- **Language**: TypeScript 5.8+

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 18.0 이상
- npm / yarn / pnpm

### 2. 패키지 설치
```bash
npm install
```

### 3. 개발 서버 실행
```bash
npm run dev
```
기본 브라우저에서 `http://localhost:3000`으로 접속하여 설명서 사이트를 확인합니다.

### 4. 프로덕션 빌드
```bash
npm run build
```

---

## 📂 프로젝트 구조

```text
juje-bot-docs/
├── src/
│   ├── App.tsx             # 사이드바 내비게이션, 모바일 토글, 룰 본문 레이아웃
│   ├── constants.ts        # 9개 주제어 게임 룰북 데이터 (GAMES 객체)
│   ├── index.css           # 디스코드 테마 전역 스타일
│   └── main.tsx            # React DOM 엔트리포인트
├── index.html              # HTML 템플릿
├── metadata.json           # 웹 애플리케이션 메타데이터
├── package.json            # 프로젝트 의존성 및 스크립트 정의
├── tsconfig.json           # TypeScript 컴파일러 설정
├── vite.config.ts          # Vite 빌드 설정
├── .env.example            # 환경변수 템플릿
├── .gitignore              # 보안 및 빌드 산출물 제외 규칙
└── README.md
```
