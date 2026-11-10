<div align="center">
  <img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# 🚇 SubwayMK (인터랙티브 가상 지하철·노선도 에디터)

> **직관적인 가상 지하철 및 버스 노선도 벡터 드로잉 웹 에디터**  
> 캔버스 위에서 자유로운 노선 드로잉, 10도 단위 스냅 각도 보정, 역 명명 및 도장 배치, 드래그 이동 및 고해상도 PNG 이미지 내보내기를 지원하는 React 19 기반 노선도 제작 스튜디오입니다.

---

## 📌 주요 특징 (Key Features)

- 🎨 **자유 곡선 및 각도 스냅 드로잉 (Angle-Snapped Routing)**
  - 마우스 드래그를 통해 자유롭게 노선을 드로잉할 수 있습니다.
  - 드로잉 중 `Shift` 키를 누르면 노선도 특유의 정형화된 형태를 제작할 수 있도록 **10도 단위 스냅 직선 보정**이 활성화됩니다.
- 🚉 **역 도장 스탬프 & 인라인 편집 (Station Stamping & Renaming)**
  - 노선 위 원하는 좌표를 클릭하여 즉시 역(`새 역`) 도장을 배치할 수 있습니다.
  - '선택 및 이동' 모드에서 역을 드래그하여 자유롭게 이동할 수 있으며, **더블 클릭**으로 역명을 실시간 수정할 수 있습니다.
- 🧽 **지우개 & 히스토리 실행 취소 (Eraser & Undo)**
  - `destination-out` 블렌딩 기반 지우개 도구를 통해 노선의 일부분을 깔끔하게 지울 수 있습니다.
  - `Ctrl + Z` 단축키 및 실행 취소 버튼을 지원하여 최근 20단계 작업 히스토리를 언제든 되돌릴 수 있습니다.
- 🌈 **12종 메트로 컬러 팔레트 & 브러시 미세 조절**
  - 수도권 전철 및 주요 노선을 상징하는 12가지 프리셋 컬러를 제공합니다.
  - 슬라이더를 통해 노선 굵기(2px ~ 60px) 및 지우개 크기(4px ~ 100px)를 실시간으로 미세 조절할 수 있습니다.
- 📸 **원클릭 고해상도 PNG 내보내기 (Export Image)**
  - 작업 중인 배경 보조 격자(Grid)는 자동으로 숨기고 노선과 역 그래픽만 선명하게 추출하여 타임스탬프가 포함된 고화질 PNG 이미지로 자동 다운로드합니다.

---

## 🛠️ 기술 스택 (Tech Stack)

- **Frontend**: React 19 (`react`, `react-dom`)
- **Graphics Engine**: HTML5 Canvas via Konva (`konva`, `react-konva`)
- **Build Tool**: Vite 6.2+
- **Styling**: Tailwind CSS v4 (`@tailwindcss/vite`, `tailwindcss`)
- **Icons**: Lucide React (`lucide-react`)
- **AI Extension Ready**: Google GenAI SDK (`@google/genai`)
- **Language**: TypeScript 5.8+

---

## 💡 에디터 조작 가이드 (Control Guide)

| 도구 / 기능 | 조작 방법 | 설명 |
| :--- | :--- | :--- |
| **자유 드로잉** | 캔버스 마우스 드래그 | 선택한 색상과 굵기로 자유 곡선 노선을 그립니다. |
| **10도 스냅 직선** | `Shift` 키를 누른 채 드래그 | 기준점에서 10도 단위로 꺾이는 깔끔한 직선 노선을 생성합니다. |
| **역 도장 찍기** | 원하는 위치 클릭 | 캔버스 위에 역 마커와 역명을 생성합니다. |
| **선택 및 이동** | 역 클릭 후 드래그 | 배치된 역의 위치를 변경합니다. |
| **역 이름 변경** | 선택 모드에서 역 더블 클릭 | 프롬프트 팝업을 통해 역명을 즉시 수정합니다. |
| **지우개** | 노선 위 마우스 드래그 | 그린 노선의 특정 부분을 부분 삭제합니다. |
| **실행 취소** | `Ctrl + Z` 또는 회전 화살표 클릭 | 직전 작업 단계로 롤백합니다. |
| **이미지로 저장** | 상단/사이드바 다운로드 버튼 | 격자를 제외한 노선도 전체를 PNG로 내보냅니다. |

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 18.0 이상
- npm 또는 yarn / pnpm

### 2. 패키지 설치
```bash
npm install
```

### 3. 환경 변수 설정 (선택 사항)
AI 기능 연동이 필요한 경우 `.env.example`을 복사하여 `.env.local`을 생성하고 API 키를 설정합니다.
```bash
cp .env.example .env.local
```
```env
GEMINI_API_KEY="your-gemini-api-key-here"
```

### 4. 로컬 개발 서버 실행
```bash
npm run dev
```
브라우저에서 `http://localhost:3000`으로 접속하여 에디터를 바로 사용할 수 있습니다.

### 5. 프로덕션 빌드
```bash
npm run build
```

---

## 📂 프로젝트 구조

```text
subway/
├── src/
│   ├── components/
│   │   ├── Canvas.tsx         # Konva 기반 노선/역/격자 렌더링 캔버스 엔진
│   │   ├── Navbar.tsx         # 상단 헤더, 초기화 및 PNG 내보내기 액션바
│   │   └── Sidebar.tsx        # 도구 선택(펜, 역, 지우개, 선택), 색상 팔레트, 굵기 슬라이더
│   ├── lib/
│   │   └── utils.ts           # Tailwind clsx/twMerge 유틸리티
│   ├── App.tsx                # 노선·역 상태, Undo 히스토리 관리 메인 컨테이너
│   ├── index.css              # 전역 스타일 및 폰트 설정
│   ├── main.tsx               # React DOM 엔트리포인트
│   └── types.ts               # 상태 및 도구 인터페이스 타입 정의
├── index.html                 # 웹 앱 템플릿
├── metadata.json              # AI Studio 앱let 메타데이터
├── package.json               # 프로젝트 의존성 및 스크립트 정의
├── tsconfig.json              # TypeScript 컴파일러 설정
├── vite.config.ts             # Vite 빌드 및 Tailwind 번들러 설정
├── .env.example               # 환경변수 템플릿
├── .gitignore                 # 보안 및 빌드 산출물 제외 규칙
└── README.md
```
