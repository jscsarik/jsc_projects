# 🌙 DreamCapture (Google AI Studio 기반 지능형 꿈 분석 & 시각화 플랫폼)

> **사용자가 기록한 꿈을 Google Gemini AI로 심층 심리 분석하고 시각적 통계를 제공하는 스마트 드림 저널**  
> Google AI Studio에서 기획·개발된 풀스택 웹 애플리케이션으로, 개인의 꿈 데이터를 로컬 SQLite에 안전하게 보관하고 최신 생성형 AI 모델과 결합하여 다채로운 해몽 및 분석을 지원합니다.

---

## 📌 주요 특징 (Key Features)

- ✍️ **체계적인 꿈 저널링 & 메타 태그 시스템**
  - 꿈을 꾼 날짜, 감정 지수(기쁨, 불안, 평온 등), 등장인물, 핵심 키워드를 일목요연하게 기록
- 🧠 **Google Gemini AI 심층 꿈 해몽 및 심리 분석**
  - 최신 `@google/genai` SDK를 통해 입력된 꿈의 상징적 의미, 무의식적 욕구, 심리 상태를 다각도로 분석
- 🎨 **모션 인터랙션 & 글래스모피즘 UI (`motion`)**
  - 부드러운 전환 애니메이션 효과와 TailwindCSS 기반의 감각적인 다크/글래스 테마 인터페이스
- 🗄️ **초고속 로컬 데이터베이스 (`better-sqlite3`)**
  - 민감한 개인 꿈 기록을 클라우드 노출 위험 없이 로컬 SQLite DB에 안전하고 영구적으로 보관

---

## 🛠️ 기술 스택 (Tech Stack)

- **Build Tool**: [Vite 6](https://vitejs.dev/)
- **Frontend**: React 19, Tailwind CSS v4, Motion (Framer Motion), Lucide React, React Datepicker
- **Routing**: React Router DOM v7
- **Backend & Database**: Express, `better-sqlite3`
- **AI Engine**: [`@google/genai`](https://www.npmjs.com/package/@google/genai) (Google Gemini API)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 20.0 이상
- [Google AI Studio](https://aistudio.google.com/) Gemini API Key

### 2. 패키지 설치
```bash
npm install
```

### 3. 환경 변수 설정
`.env.example`을 복사하여 `.env.local`을 생성하고 Gemini API 키를 입력합니다.
```bash
cp .env.example .env.local
```

`.env.local` 내용:
```env
GEMINI_API_KEY="your-gemini-api-key-here"
APP_URL="http://localhost:3000"
```

### 4. 로컬 개발 서버 실행
```bash
npm run dev
```
브라우저에서 `http://localhost:3000`으로 접속합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── src/
│   ├── components/          # 공통 레이아웃, 네비게이션바, 히어로 배너 UI
│   ├── pages/               # 홈, 꿈 기록(Reservation), 포트폴리오, FAQ 페이지
│   ├── lib/                 # 유틸리티 함수 및 스타일 헬퍼
│   ├── App.tsx              # 라우팅 및 전역 상태 관리
│   └── main.tsx             # React DOM 마운트 엔트리포인트
├── public/                  # 정적 이미지 및 갤러리 에셋
├── .env.example             # 환경변수 템플릿
├── metadata.json            # Google AI Studio 앱 메타데이터
├── vite.config.ts           # Vite 설정
└── package.json
```
