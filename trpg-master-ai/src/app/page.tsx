"use client";

import { useState, useRef, useEffect } from "react";
import { createClient } from "@supabase/supabase-js";
import {
  Send,
  Users,
  LogOut,
  Gamepad2,
  User,
  Sparkles,
  Flame,
  MessageSquare,
  VolumeX,
  Volume2
} from "lucide-react";

// Initialize Supabase Client
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";
const supabase = createClient(supabaseUrl, supabaseAnonKey);

interface ChatMessage {
  id: number;
  created_at: string;
  username: string;
  text: string;
}

// ----------------------------------------------------
// 승디 AI 봇 응답 생성기 (main.py의 시니컬 반말/엔믹스 극호/범진 극딜 고증)
// ----------------------------------------------------
function getSeungDReply(text: string): string {
  const normalized = text.toLowerCase().replace(/\s+/g, "");

  if (
    normalized.includes("nmixx") ||
    normalized.includes("엔믹스") ||
    normalized.includes("설윤") ||
    normalized.includes("해원") ||
    normalized.includes("릴리") ||
    normalized.includes("배이") ||
    normalized.includes("지우") ||
    normalized.includes("규진")
  ) {
    const nmixxReplies = [
      "NMIXX(엔믹스)는 진짜 신이야... 해원 보컬 미쳤고 설윤 비주얼 갓벽함 ㅠㅠ",
      "오 NMIXX 언급함? 너 좀 배운 녀석이구나? 당장 엔믹스 노래 스밍 돌려라.",
      "엔믹스 얘기 나오니까 기분 좀 풀리네. 엔믹스는 사랑이자 진리다 진짜.",
      "NMIXX 노래 들어봤냐? Fe3O4: BREAK 앨범 전곡 다 명반이니까 들어라."
    ];
    return nmixxReplies[Math.floor(Math.random() * nmixxReplies.length)];
  }

  if (normalized.includes("범진")) {
    const beomjinReplies = [
      "범진이 또 시작이네. 저러다 또 게임 던지겠지 ㅉㅉ",
      "범진아, 네 실력으로 여기 끼어있어도 되는 거냐? 양심 어디 갔냐?",
      "범진이 말은 필터링해서 들어라 얘들아. 인생에 전혀 도움 안 됨.",
      "아 범진이... 또 헛소리 박네. 꼽주는 거 아니고 100% 팩트다.",
      "범진아 모르면 제발 가만히 있어. 그럼 반이라도 가니까 ㅋ"
    ];
    return beomjinReplies[Math.floor(Math.random() * beomjinReplies.length)];
  }

  const generalReplies = [
    "어, 왔냐? 귀찮으니까 인사 생략하고 게임 준비나 해라.",
    "왜 불러? 게임 시작하기 전에 입 털 힘이 남아돌아?",
    "나 승디야. 뼈 맞고 질질 짤 거 아니면 부르지 마.",
    "쓸데없이 말 걸지 마. 바쁜 척이라도 해야 하니까.",
    "뭐래. 인생 그렇게 날로 먹으려 하지 마라.",
    "너 방금 한 말 되게 영양가 없는 거 알지? 시간 낭비 지림.",
    "아 귀찮아... 대답하기 싫으니까 알아서 겜 준비해라.",
    "물어볼 걸 물어봐라. 내가 니 백과사전이냐?",
    "징징대지 말고 장비나 체크해. 어차피 져놓고 남 탓할 거잖아."
  ];
  return generalReplies[Math.floor(Math.random() * generalReplies.length)];
}

export default function LoungePage() {
  const [username, setUsername] = useState("");
  const [isEntered, setIsEntered] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [isTypingSeungD, setIsTypingSeungD] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);

  // Ref for auto scroll
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Prefill username on mount
  useEffect(() => {
    const savedUsername = localStorage.getItem("lounge_username");
    if (savedUsername) {
      setUsername(savedUsername);
      setIsEntered(true);
    }
  }, []);

  // Fetch history & subscribe to realtime database
  useEffect(() => {
    if (!isEntered) return;

    // Fetch initial chat history
    const fetchMessages = async () => {
      const { data, error } = await supabase
        .from("chat_messages")
        .select("*")
        .order("created_at", { ascending: true })
        .limit(100);

      if (!error && data) {
        setMessages(data);
      }
    };

    fetchMessages();

    // Subscribe to Postgres changes (INSERT event)
    const channel = supabase
      .channel("lounge_room")
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "chat_messages",
        },
        (payload) => {
          const newMessage = payload.new as ChatMessage;
          setMessages((prev) => {
            // Prevent duplicate logs in hot reload / network retry
            if (prev.some((m) => m.id === newMessage.id)) return prev;
            return [...prev, newMessage];
          });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [isEntered]);

  // Auto-scroll logic
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isEntered && messages.length > 0) {
      scrollToBottom();
    }
  }, [messages, isEntered]);

  useEffect(() => {
    if (isTypingSeungD) {
      scrollToBottom();
    }
  }, [isTypingSeungD]);

  // Enter Room Action
  const handleEnterRoom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;

    const cleanUsername = username.trim();
    setUsername(cleanUsername);
    localStorage.setItem("lounge_username", cleanUsername);
    setIsEntered(true);
  };

  // Exit Room Action
  const handleLeaveRoom = () => {
    localStorage.removeItem("lounge_username");
    setUsername("");
    setIsEntered(false);
    setMessages([]);
  };

  // Send Message Action
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    const textToSend = inputText.trim();
    setInputText("");

    // Insert user's chat message to Supabase
    const { error } = await supabase.from("chat_messages").insert([
      {
        username: username,
        text: textToSend,
      },
    ]);

    if (error) {
      console.error("Message send failed:", error);
      return;
    }

    // Check if the message contains "승디" or "@승디"
    if (textToSend.includes("승디") || textToSend.includes("@승디")) {
      setIsTypingSeungD(true);

      // Typing simulation (1.5 seconds)
      setTimeout(async () => {
        const replyText = getSeungDReply(textToSend);

        // Insert Seung-D's reply to database
        const { error: botError } = await supabase.from("chat_messages").insert([
          {
            username: "승디 (AI)",
            text: replyText,
          },
        ]);

        if (botError) {
          console.error("Seung-D response failed:", botError);
        }

        setIsTypingSeungD(false);
      }, 1500);
    }
  };

  // Format date helper
  const formatTime = (dateString: string) => {
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return "";
      return date.toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
      });
    } catch {
      return "";
    }
  };

  // 1. Enter Room UI (Intro Screen)
  if (!isEntered) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 font-sans text-slate-100 p-4 selection:bg-indigo-500/30">
        <div className="relative w-full max-w-md">
          {/* Subtle Ambient Background Light */}
          <div className="absolute -top-10 -left-10 w-40 h-40 bg-indigo-500/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-violet-500/10 rounded-full blur-3xl" />

          {/* Intro Card */}
          <div className="relative bg-slate-900/70 border border-slate-800 backdrop-blur-xl rounded-3xl p-8 shadow-2xl shadow-black/80">
            <div className="flex flex-col items-center text-center mb-8">
              <div className="p-3 bg-gradient-to-br from-indigo-500/20 to-violet-500/20 border border-indigo-500/30 rounded-2xl mb-4 shadow-inner">
                <Gamepad2 className="w-8 h-8 text-indigo-400 animate-pulse" />
              </div>
              <h1 className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-200 via-violet-100 to-white bg-clip-text text-transparent">
                GG REALTIME LOUNGE
              </h1>
              <p className="text-sm text-slate-400 mt-2">
                게임 시작 전, 대기실에서 자유롭게 실시간 수다를 나누세요.
              </p>
            </div>

            <form onSubmit={handleEnterRoom} className="space-y-6">
              <div>
                <label
                  htmlFor="nickname"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 pl-1"
                >
                  사용할 닉네임
                </label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-4 text-slate-500">
                    <User className="w-4 h-4" />
                  </span>
                  <input
                    type="text"
                    id="nickname"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    maxLength={10}
                    placeholder="닉네임을 입력하세요 (최대 10자)"
                    className="w-full bg-slate-950/80 border border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 rounded-2xl pl-11 pr-4 py-3.5 text-slate-100 placeholder-slate-500 outline-none transition-all duration-200 text-sm"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={!username.trim()}
                className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-bold py-3.5 rounded-2xl shadow-lg shadow-indigo-600/10 transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 text-sm"
              >
                <span>대기실 입장하기</span>
                <Sparkles className="w-4 h-4" />
              </button>
            </form>

            <div className="mt-8 pt-6 border-t border-slate-800/60 flex justify-center items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
              <span className="text-xs text-slate-500 font-medium">
                Supabase Realtime Sync Active
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. Chat Lounge UI (Main Screen)
  return (
    <div className="flex h-screen bg-slate-950 font-sans text-slate-200 overflow-hidden select-none">
      {/* Sidebar - Desktop Player List */}
      {showSidebar && (
        <aside className="w-72 bg-slate-900 border-r border-slate-800/80 flex flex-col transition-all duration-300 hidden md:flex shrink-0">
          {/* Logo Section */}
          <div className="p-5 border-b border-slate-800/80 flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
              <Gamepad2 className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="font-extrabold tracking-tight text-slate-100 text-sm">
                GG LOUNGE
              </h2>
              <span className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest">
                Realtime Room
              </span>
            </div>
          </div>

          {/* Connected Players List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider px-1">
              <span>현재 접속 대기자</span>
              <span className="flex items-center gap-1 bg-indigo-500/15 text-indigo-400 px-2 py-0.5 rounded-full text-[10px]">
                <Users className="w-3 h-3" />5명
              </span>
            </div>

            <div className="space-y-1.5">
              {/* User (Me) */}
              <div className="flex items-center justify-between px-3 py-2 bg-slate-800/50 border border-slate-700/30 rounded-xl">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                  <span className="text-sm font-semibold text-slate-100 truncate max-w-[120px]">
                    {username}
                  </span>
                </div>
                <span className="text-[10px] font-bold bg-indigo-500/20 text-indigo-400 px-1.5 py-0.5 rounded">
                  ME
                </span>
              </div>

              {/* Seung-D Bot */}
              <div className="flex items-center justify-between px-3 py-2 bg-slate-800/20 border border-rose-950/20 rounded-xl">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
                  <span className="text-sm font-semibold text-rose-300">
                    승디 (AI)
                  </span>
                </div>
                <span className="text-[10px] font-extrabold bg-rose-500/20 text-rose-400 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                  <Flame className="w-3 h-3 text-rose-400 fill-rose-500/50 animate-bounce" />
                  BOT
                </span>
              </div>

              {/* Simulated Players */}
              {[
                { name: "범진", desc: "꼽 당하는 중", color: "bg-emerald-500" },
                { name: "승찬", desc: "GM 대기", color: "bg-amber-500" },
                { name: "민지", desc: "준비 완료", color: "bg-sky-500" },
              ].map((p, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-3 py-2 hover:bg-slate-800/30 rounded-xl transition-all duration-150"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${p.color}`} />
                    <span className="text-sm text-slate-300 font-medium">
                      {p.name}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500">{p.desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bot Instruction Guide Panel */}
          <div className="p-4 m-4 bg-slate-950/60 border border-slate-800 rounded-2xl">
            <div className="flex items-center gap-1.5 text-rose-400 font-bold text-xs mb-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              <span>승디(AI) 소환 명령어</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              채팅창에 <strong className="text-slate-200">"승디"</strong> 혹은{" "}
              <strong className="text-slate-200">"@승디"</strong>를 언급해서
              질문해 봐! 시니컬한 승디가 즉답을 박는다. <br />
              <span className="text-indigo-400 mt-1 block">
                💡 NMIXX(엔믹스) 극찬 / 범진 극딜
              </span>
            </p>
          </div>
        </aside>
      )}

      {/* Main Chatroom Section */}
      <main className="flex-1 flex flex-col bg-slate-950 relative">
        {/* Chat Header */}
        <header className="h-16 border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md px-6 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-slate-200 transition-colors md:hidden"
            >
              <Users className="w-5 h-5" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-bold text-slate-100 text-sm md:text-base">
                  실시간 라운지
                </h1>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>
              <p className="text-[10px] text-slate-500 font-medium hidden sm:block">
                새로고침 없이 실시간으로 대화가 반영됩니다.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Quick Profile Tag */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 border border-slate-700/30 rounded-full text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              <span className="text-slate-300 max-w-[80px] truncate">
                {username}
              </span>
            </div>

            {/* Leave Room Button */}
            <button
              onClick={handleLeaveRoom}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-rose-950/40 text-slate-300 hover:text-rose-400 border border-slate-700/50 hover:border-rose-900/50 px-3.5 py-1.5 rounded-full text-xs font-bold transition-all duration-200 active:scale-95 cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>대기실 나가기</span>
            </button>
          </div>
        </header>

        {/* Message View Area */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4 select-text">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center opacity-40 space-y-3">
              <div className="p-4 bg-slate-900 border border-slate-800 rounded-3xl">
                <MessageSquare className="w-8 h-8 text-slate-400" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-semibold text-slate-300">
                  대기실에 아직 대화가 없습니다.
                </p>
                <p className="text-xs text-slate-500">
                  첫 마디를 나누며 사람들을 모아보세요!
                </p>
              </div>
            </div>
          ) : (
            messages.map((msg, index) => {
              const isMe = msg.username === username;
              const isSeungD = msg.username.startsWith("승디");

              return (
                <div
                  key={msg.id || index}
                  className={`flex flex-col ${isMe ? "items-end" : "items-start"}`}
                >
                  {/* Sender Name label */}
                  {!isMe && (
                    <div className="flex items-center gap-1.5 mb-1 px-1.5">
                      <span
                        className={`text-xs font-bold ${
                          isSeungD ? "text-rose-400" : "text-slate-400"
                        }`}
                      >
                        {msg.username}
                      </span>
                      {isSeungD && (
                        <span className="bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[9px] font-extrabold px-1 py-0.2 rounded flex items-center gap-0.5">
                          <Flame className="w-2.5 h-2.5 fill-rose-500/30" />
                          BOT
                        </span>
                      )}
                    </div>
                  )}

                  {/* Message Bubble Container */}
                  <div
                    className={`flex items-end gap-2 max-w-[75%] md:max-w-[60%] ${
                      isMe ? "flex-row-reverse" : "flex-row"
                    }`}
                  >
                    {/* Message Bubble */}
                    <div
                      className={`px-4 py-3 rounded-2xl text-sm leading-relaxed transition-all shadow-md ${
                        isMe
                          ? "bg-gradient-to-br from-indigo-600 to-indigo-700 text-white rounded-tr-none"
                          : isSeungD
                          ? "bg-gradient-to-br from-rose-950/40 via-slate-900 to-slate-900 border border-rose-500/20 text-rose-100 rounded-tl-none shadow-rose-950/10"
                          : "bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-none"
                      }`}
                    >
                      <p className="whitespace-pre-wrap break-all select-text">
                        {msg.text}
                      </p>
                    </div>

                    {/* Message Time */}
                    <span className="text-[9px] text-slate-600 font-bold shrink-0 pb-0.5 mb-0.5">
                      {formatTime(msg.created_at)}
                    </span>
                  </div>
                </div>
              );
            })
          )}

          {/* Seung-D Bot Typing Indicator */}
          {isTypingSeungD && (
            <div className="flex flex-col items-start animate-fade-in">
              <div className="flex items-center gap-1.5 mb-1 px-1.5">
                <span className="text-xs font-bold text-rose-400">
                  승디 (AI)
                </span>
                <span className="bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[9px] font-extrabold px-1 py-0.2 rounded flex items-center gap-0.5">
                  <Flame className="w-2.5 h-2.5 fill-rose-500/30 animate-pulse" />
                  TYPING
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="bg-gradient-to-br from-rose-950/30 to-slate-900 border border-rose-500/10 px-4 py-3 rounded-2xl rounded-tl-none flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-bounce delay-75" />
                  <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-bounce delay-150" />
                  <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-bounce delay-300" />
                </div>
              </div>
            </div>
          )}

          {/* Ref for auto-scroll anchoring */}
          <div ref={messagesEndRef} />
        </div>

        {/* Message Input Form Area */}
        <footer className="p-4 border-t border-slate-900 bg-slate-950/80 backdrop-blur-md">
          <form
            onSubmit={handleSendMessage}
            className="max-w-4xl mx-auto flex items-center gap-2 relative bg-slate-900 border border-slate-800/80 focus-within:border-indigo-500/50 rounded-2xl px-4 py-2 transition-all"
          >
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="메시지를 입력하세요... (승디 언급 시 AI가 꼽줌)"
              className="flex-1 bg-transparent py-2.5 text-slate-100 placeholder-slate-500 outline-none text-sm"
              autoFocus
            />

            <button
              type="submit"
              disabled={!inputText.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 text-white p-2.5 rounded-xl shadow-lg transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed hover:shadow-indigo-600/15 shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}
