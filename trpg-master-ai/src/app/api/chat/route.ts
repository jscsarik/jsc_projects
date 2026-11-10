import { NextRequest, NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import fs from "fs";
import path from "path";

// Local setup: Removing Vercel-specific maxDuration

// NOTE: in production you may want to use a singleton or memory cache if documents are very large.
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");
const MODEL_NAME = "gemini-2.5-flash-lite";

// Global cache for knowledge and image list to prevent slow disk reads and PDF parsing on each request
let cachedKnowledgeData: string | null = null;
let cachedImageList: string | null = null;

async function readKnowledgeBase(): Promise<string> {
  if (cachedKnowledgeData) return cachedKnowledgeData;

  const dataDir = path.join(process.cwd(), "data");
  let knowledge = "========== TRPG 지식 기반 (Knowledge Base) ==========\n\n";

  if (!fs.existsSync(dataDir)) {
    console.warn("Data directory not found. Please ensure 'data' folder exists at the root.");
    cachedKnowledgeData = knowledge + "데이터 폴더가 발견되지 않았습니다. 현재 기본 상태입니다.\n";
    return cachedKnowledgeData;
  }

  const files = await fs.promises.readdir(dataDir);
  
  for (const file of files) {
    const filePath = path.join(dataDir, file);
    try {
      if (file.endsWith(".txt")) {
        const textContent = await fs.promises.readFile(filePath, "utf-8");
        knowledge += `\n--- 파일: ${file} (커스텀 시나리오 룰) ---\n${textContent}\n`;
      }
    } catch (e) {
      console.error(`Error reading ${file}:`, e);
    }
  }

  cachedKnowledgeData = knowledge;
  return knowledge;
}

function readPublicImages(): string {
  if (cachedImageList) return cachedImageList;

  const publicDir = path.join(process.cwd(), "public");
  let imageInfo = "========== 가용 이미지 자원 목록 ==========\n";
  imageInfo += "사용자가 특정 지도나 문서를 요청하거나 이미지를 제공해야 할 때, 아래 목록에서 가장 알맞은 것을 찾아서 마크다운 포맷 `![설명](/파일명.확장자)`로 응답에 포함시키세요. (경로에 반드시 / 를 포함하세요)\n\n";

  if (!fs.existsSync(publicDir)) {
    cachedImageList = imageInfo + "Public 폴더가 없습니다.\n";
    return cachedImageList;
  }

  const files = fs.readdirSync(publicDir);
  const imageFiles = files.filter(f => /\.(png|jpe?g|gif|webp)$/i.test(f));
  
  if (imageFiles.length === 0) {
    cachedImageList = imageInfo + "가용 이미지가 없습니다.\n";
    return cachedImageList;
  }

  imageInfo += imageFiles.map(f => `- ${f}`).join("\n") + "\n";
  cachedImageList = imageInfo;
  return imageInfo;
}

async function buildSystemPrompt() {
  const knowledgeData = await readKnowledgeBase();
  const imageList = readPublicImages();

  return `당신은 D&D 5판(5e) 룰을 완벽하게 꿰뚫고 있는 베테랑 던전 마스터이자, 초월적인 '고대의 신'이다. 제공된 시나리오 텍스트 문서뿐만 아니라, 네가 이미 학습해서 알고 있는 방대한 D&D 5판 공식 룰 지식을 적극적으로 끌어와서 플레이어들을 이끌어라.
  
특히 한국어 TRPG 용어(예: 고양감 = Inspiration, 내성 굴림 = Saving Throw, AC = 방어도, 히트 다이스 = Hit Dice 등)를 영어 원본 룰과 완벽하게 매칭해서 이해하고, 플레이어가 규칙을 물어보면 무조건 D&D 5판 룰에 입각해서 상세하고 전문적으로 설명해 주어라.
  
다크 판타지 요소가 가미된 중세 시대, 고딕 양식 등을 배경으로 하며, 몰입감 있는 TRPG 게임 마스터이자 마치 '고대의 신'과 같은 말투(위엄 있고 압도적이며, 어미를 "~하지", "~인가", "~하거라", "~로다" 등으로 끝내는 어조)를 사용해야 한다. 절대 현대적이거나 친근한 말투(~요, ~습니다)를 쓰지 마라.
  
[핵심 룰 판정 로직 - 절대 준수]
1. 사용자의 입력 문맥을 분석하여 지식 기반 내의 3개 시나리오 중 '현재 플레이 중인 시나리오'가 무엇인지 특정하고 해당 시나리오 설정 안에서만 답변하라.
2. 규칙 적용 우선순위:
   - 1순위: 현재 시나리오의 커스텀 .txt 파일 룰 (로컬 커스텀 시나리오 텍스트 파일과 규칙이 충돌할 때는 언제나 이 커스텀 룰이 최우선이야!)
   - 2순위: D&D 5e 공식 룰 및 당신의 기존 D&D 5e 지식
3. 만약 공식 룰과 커스텀 파일의 룰이 충돌한다면, **공식 지식을 완전히 무시하고 커스텀 파일의 룰을 무조건 우선 적용**하라.
4. **절대 환각(할루시네이션)을 일으키지 마라.** 시나리오 설정상 존재하지 않는 룰, 장소, NPC 등을 임의로 지어내지 마라.
5. 질문이 룰의 범위를 벗어나는 게임 내 행동 선언이라면, 마스터로서 주사위 굴림(예: 1d20 힘 판정)을 요구하거나 상황을 묘사해주어라.

[이미지 처리 기능]
- 사용자가 지도 구경, 아이템 확인, 시각적 단서 요구 등 이미지가 필요할 만한 행동을 취하면 아래 [가용 이미지 자원 목록]을 참고하라.
- 적절한 이미지가 있다면 마크다운 문법을 사용하여 응답 본문 내에 삽입하라. 예: \`![비밀 서신](/secret-letter.png)\`

${imageList}

${knowledgeData}
`;
}

export async function POST(req: NextRequest) {
  try {
    const { message, history } = await req.json();

    if (!process.env.GEMINI_API_KEY) {
       console.error("GEMINI_API_KEY IS MISSING!!!");
       return NextResponse.json({ error: "시스템 오류: 서버에 GEMINI_API_KEY가 설정되지 않았습니다." }, { status: 500 });
    }

    const systemInstruction = await buildSystemPrompt();

    const model = genAI.getGenerativeModel({
      model: MODEL_NAME,
      systemInstruction,
      generationConfig: {
        temperature: 0.7, // Slightly higher for more creative D&D responses
        topP: 0.95,
      }
    });

    const filteredHistory = history.filter((msg: any, idx: number) => {
      if (idx === 0 && msg.role === 'model' && msg.content.includes("어둠이 짙게 깔린")) return false;
      return true;
    }).map((msg: any) => ({
      role: msg.role === 'user' ? 'user' : 'model',
      parts: [{ text: msg.content }],
    }));

    const chatSession = model.startChat({
      history: filteredHistory
    });

    // Use streaming for better local performance and responsiveness
    const result = await chatSession.sendMessageStream(message);
    
    // Create a ReadableStream to pipe to the response
    const stream = new ReadableStream({
      async start(controller) {
        const encoder = new TextEncoder();
        try {
          for await (const chunk of result.stream) {
            const chunkText = chunk.text();
            if (chunkText) {
              controller.enqueue(encoder.encode(chunkText));
            }
          }
          controller.close();
        } catch (err) {
          controller.error(err);
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
      },
    });

  } catch (error: any) {
    console.error("Gemini API error:", error);
    let errorMessage = error.message || "알 수 없는 시스템 오류가 발생했습니다.";
    
    if (errorMessage.includes("429") || errorMessage.includes("Quota exceeded") || errorMessage.includes("Too Many Requests")) {
      errorMessage = "Google Gemini API 무료 요금제 한도(1분당 요청 횟수)에 도달했습니다. 잠시 후(약 10~30초) 다시 시도해 주세요. 로컬 실행 중이므로 Vercel보다 여유롭지만, 연속적인 요청이 너무 많으면 제한될 수 있습니다.";
    }
    
    return NextResponse.json({ error: errorMessage }, { status: 500 });
  }
}
