# 🌙 DreamCapture (Google AI Studio 기반 지능형 꿈 분석 & 시각화 플랫폼)

> **꿈의 내용을 기록하고 Google Gemini AI를 통해 심층 심리 분석 및 시각적 스토리텔링을 제공하는 스마트 드림 저널**  
> Google AI Studio에서 기획·개발된 풀스택 웹 애플리케이션으로, 수면 및 꿈 데이터베이스를 로컬 SQLite에 보관하고 생성형 AI를 결합한 인터랙티브 분석을 지원합니다.

---

## 📌 주요 기능

- ✍️ **지능형 꿈 저널링 & 태그 시스템**
  - 꿈을 꾼 날짜, 감정 상태, 등장인물, 핵심 키워드를 체계적으로 기록
- 🧠 **Google Gemini AI 심층 꿈 해몽 & 심리 분석**
  - 최신 `@google/genai` SDK를 연동하여 입력된 꿈 텍스트의 상징적 의미 및 무의식 심리 분석
- 🎨 **모션 인터랙션 & 현대적인 UI (`motion`)**
  - 부드러운 애니메이션 효과와 TailwindCSS 기반의 세련된 다크/글래스 테마
- 🗄️ **초고속 로컬 데이터베이스 (`better-sqlite3`)**
  - 사용자의 민감한 개인 꿈 기록을 브라우저/로컬 환경에 안전하고 빠르게 영구 보관

---

## 🛠️ 기술 스택

- **Build Tool**: [Vite 6](https://vitejs.dev/)
- **Frontend**: React 19, Tailwind CSS v4, Motion (Framer Motion), Lucide React, React Datepicker
- **Routing**: React Router DOM v7
- **Backend / Database**: Express, `better-sqlite3`
- **AI Engine**: [`@google/genai`](https://www.npmjs.com/package/@google/genai) (Google Gemini API)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 20+ 이상
- [Google AI Studio](https://aistudio.google.com/) Gemini API Key

### 2. 의존성 설치
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

## 📂 프로젝트 구조

```text
├── src/                    # React 프론트엔드 및 AI 분석 로직
├── public/                 # 정적 리소스
├── .env.example            # 환경변수 템플릿
├── metadata.json           # Google AI Studio 앱 메타데이터
├── vite.config.ts          # Vite 번들러 설정
└── package.json
```
