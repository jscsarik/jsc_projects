# 🐉 TRPG Master AI (Google Gemini 기반 지능형 TRPG 세션 마스터)

> **Google Gemini 대규모 언어 모델(LLM)을 게임 마스터(DM/GM)로 탑재한 인터랙티브 롤플레잉 플랫폼**  
> D&D 5e 공식 룰북과 다채로운 창작 시나리오(군웅할거, 수미상관, 이정학 토벌전) 데이터를 주입받아 유저의 선택에 유기적으로 반응하며 몰입도 높은 스토리를 실시간으로 이끌어갑니다.

---

## 📌 주요 특징 (Key Features)

- 🎲 **지능형 AI 게임 마스터 (DM Mode)**
  - Google Gemini API를 활용한 상황 묘사, 주사위 판정 계산, NPC 대화 및 전투 밸런스 중재
  - 플레이어의 돌발 행동과 자유도 높은 대사에도 규칙에 기반하여 유연하게 반응
- 📜 **정밀한 룰셋 & 방대한 시나리오 데이터베이스 (`data/`)**
  - **D&D 5th Edition Basic Rules** 공식 룰셋 탑재
  - **3대 테마 시나리오 기본 제공**:
    - **군웅할거 (Warring States)**: 종족, 직업, 고유 갑옷/무기/마법 체계가 포함된 세력 쟁패 대서사
    - **수미상관 (Sumi-Sang-Gwan)**: 몬스터, 장비, 종족 및 전용 직업군이 맞물린 미스터리 어드벤처
    - **이정학 토벌전 (Raid on Lee Jeong-Hak)**: 캐릭터 프리셋, 보스 레이드 기믹, 전용 마법과 아이템이 준비된 결전 시나리오
- 🗺️ **시나리오 맵 & 비주얼 아트워크 (`public/`)**
  - 군웅할거 지도(`gunung_map.png`), 수미상관 지도(`sumi_map.png`)
  - 성채 및 내부 도면(`Lee_castle.png`, `Lee_Castle_inside_Drawing.png`), 주점(`Lee_dark_bar.png`) 등 고해상도 비주얼 맵 실시간 렌더링
- ⚡ **실시간 마크다운 스트리밍**
  - `react-markdown`을 통한 부드러운 텍스트 스트리밍과 주사위 판정 테이블 가독성 극대화

---

## 🛠️ 기술 스택 (Tech Stack)

- **Framework**: [Next.js 16 (App Router)](https://nextjs.org/)
- **Frontend**: React 19, TypeScript, Tailwind CSS, Lucide React, `react-markdown`
- **AI Engine**: [`@google/generative-ai`](https://www.npmjs.com/package/@google/generative-ai) (Google Gemini API)
- **Database & Sync**: Supabase (`@supabase/supabase-js`)

---

## 🚀 빠른 시작 (Getting Started)

### 1. 사전 요구사항
- Node.js 18.17 이상 (권장: Node.js 20+)
- [Google AI Studio](https://aistudio.google.com/)에서 발급받은 Gemini API Key

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
# Google Gemini API Key
GEMINI_API_KEY=your-gemini-api-key-here
GOOGLE_GENERATIVE_AI_API_KEY=your-gemini-api-key-here
```

### 4. 로컬 개발 서버 실행
본 프로젝트의 기본 포트는 **`62010`**으로 지정되어 있습니다.
```bash
npm run dev
```

브라우저에서 아래 주소로 접속합니다:
- **로컬 주소**: `http://localhost:62010`
- **사설/외부망 연결 시**: `http://<서버-IP>:62010`

---

## 📂 프로젝트 구조 (Project Structure)

```text
├── data/                    # TRPG 공식 룰북 및 시나리오 텍스트 데이터
│   ├── dnd_5e_basic_rules.* # D&D 5판 기본 규칙
│   ├── 군웅할거_*.txt        # 시나리오, 룰, 장비, 종족/직업 정보
│   ├── 수미상관_*.txt        # 시나리오, 몬스터, 장비, 종족/직업 정보
│   └── 이정학_토벌전_*.txt    # 레이드 시나리오, 캐릭터, 마법, 아이템
├── public/                  # 지도 및 던전/성채 일러스트 에셋
├── src/
│   ├── app/
│   │   ├── api/chat/route.ts # Gemini LLM 프롬프트 주입 및 스트리밍 응답 API
│   │   ├── layout.tsx       # 레이아웃
│   │   └── page.tsx         # 메인 TRPG 세션 인터랙티브 UI
├── .env.example             # 환경변수 템플릿
├── next.config.ts           # Next.js 설정
└── package.json
```
