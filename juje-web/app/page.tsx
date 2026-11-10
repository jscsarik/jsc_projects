'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Send, 
  Users, 
  LogOut, 
  Volume2, 
  VolumeX, 
  MessageSquare, 
  Clock, 
  Sparkles, 
  User,
  Wifi,
  ChevronRight,
  Copy,
  Check,
  PlusCircle,
  LogIn,
  Play,
  RotateCcw,
  Eye,
  HelpCircle,
  List,
  AlertTriangle,
  Skull,
  Heart
} from 'lucide-react';
import { supabase } from '@/lib/supabase';
import { LIAR_WORDS } from '@/lib/words';

interface Message {
  id: string | number;
  created_at: string;
  username: string;
  text: string;
  room_id: string;
}

interface OnlineUser {
  username: string;
  online_at: string;
}

// Helper to generate initials for avatar
const getInitials = (name: string) => {
  if (!name) return '?';
  return name.trim().charAt(0).toUpperCase();
};

// Cozy Playful Gradient generator
const getAvatarGradient = (name: string) => {
  const gradients = [
    'from-rose-300 to-orange-300',
    'from-peach-300 to-amber-300',
    'from-amber-200 to-yellow-300',
    'from-teal-300 to-emerald-300',
    'from-sky-300 to-indigo-300',
    'from-fuchsia-300 to-pink-300',
    'from-coral-300 to-rose-300',
    'from-orange-300 to-yellow-300',
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % gradients.length;
  return gradients[index];
};

export default function Home() {
  // Authentication & Mounting states
  const [inputUsername, setInputUsername] = useState('');
  const [username, setUsername] = useState('');
  const [isMounted, setIsMounted] = useState(false);
  const [showRulesGuide, setShowRulesGuide] = useState(false);
  const [isEnvMissing, setIsEnvMissing] = useState(false);

  // Room states
  const [roomMode, setRoomMode] = useState<'join' | 'create'>('join');
  const [roomType, setRoomType] = useState<'chat' | 'liar'>('chat');
  const [inputRoomId, setInputRoomId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [copied, setCopied] = useState(false);

  // Chat Room states
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([]);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // Liar Game states
  const [gameStatus, setGameStatus] = useState<'waiting' | 'speaking' | 'voting' | 'defense' | 'liar_guess' | 'result' | 'final_scoreboard'>('waiting');
  const [gameCategory, setGameCategory] = useState('');
  const [gameWord, setGameWord] = useState('');
  const [gameLiar, setGameLiar] = useState('');

  // 3-Round Game details (Python aligned)
  const [round, setRound] = useState(1);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [speakingOrder, setSpeakingOrder] = useState<string[]>([]);
  const [currentSpeakerIndex, setCurrentSpeakerIndex] = useState(0);
  const [timerSeconds, setTimerSeconds] = useState(0);
  
  // Voting & Defense details
  const [votes, setVotes] = useState<Record<string, string>>({}); // Key: voter, Value: target username / 'skip' / 'one_more'
  const [nominatedPlayer, setNominatedPlayer] = useState('');
  const [trialNumber, setTrialNumber] = useState<number>(1); // 1, 2, 3 (Trial stage)
  const [defenseVotes, setDefenseVotes] = useState<Record<string, 'kill' | 'spare'>>({}); // Key: voter, Value: 'kill' / 'spare'
  
  // Speech history tracking
  const [descriptions, setDescriptions] = useState<Record<string, string[]>>({}); // Key: username, Value: list of speeches
  const [showSpeechHistory, setShowSpeechHistory] = useState(false);

  // Game input states
  const [liarGuessText, setLiarGuessText] = useState('');
  const [caught, setCaught] = useState(false);

  // Refs for scrolling, state tracking, and websocket channel access
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const activeUsernameRef = useRef('');
  const chatChannelRef = useRef<any>(null);

  // Game state refs to prevent React state closure locking in Realtime events
  const gameStatusRef = useRef<'waiting' | 'speaking' | 'voting' | 'defense' | 'liar_guess' | 'result' | 'final_scoreboard'>('waiting');
  const gameCategoryRef = useRef('');
  const gameWordRef = useRef('');
  const gameLiarRef = useRef('');
  const roundRef = useRef(1);
  const scoresRef = useRef<Record<string, number>>({});
  const currentSpeakerIndexRef = useRef(0);
  const speakingOrderRef = useRef<string[]>([]);
  const timerSecondsRef = useRef(0);
  const votesRef = useRef<Record<string, string>>({});
  const nominatedPlayerRef = useRef('');
  const trialNumberRef = useRef<number>(1);
  const defenseVotesRef = useRef<Record<string, 'kill' | 'spare'>>({});
  const descriptionsRef = useRef<Record<string, string[]>>({});
  const caughtRef = useRef(false);
  const onlineUsersRef = useRef<OnlineUser[]>([]);

  // Sync refs with React state
  useEffect(() => { gameStatusRef.current = gameStatus; }, [gameStatus]);
  useEffect(() => { gameCategoryRef.current = gameCategory; }, [gameCategory]);
  useEffect(() => { gameWordRef.current = gameWord; }, [gameWord]);
  useEffect(() => { gameLiarRef.current = gameLiar; }, [gameLiar]);
  useEffect(() => { roundRef.current = round; }, [round]);
  useEffect(() => { scoresRef.current = scores; }, [scores]);
  useEffect(() => { currentSpeakerIndexRef.current = currentSpeakerIndex; }, [currentSpeakerIndex]);
  useEffect(() => { speakingOrderRef.current = speakingOrder; }, [speakingOrder]);
  useEffect(() => { timerSecondsRef.current = timerSeconds; }, [timerSeconds]);
  useEffect(() => { votesRef.current = votes; }, [votes]);
  useEffect(() => { nominatedPlayerRef.current = nominatedPlayer; }, [nominatedPlayer]);
  useEffect(() => { trialNumberRef.current = trialNumber; }, [trialNumber]);
  useEffect(() => { defenseVotesRef.current = defenseVotes; }, [defenseVotes]);
  useEffect(() => { descriptionsRef.current = descriptions; }, [descriptions]);
  useEffect(() => { caughtRef.current = caught; }, [caught]);
  useEffect(() => { onlineUsersRef.current = onlineUsers; }, [onlineUsers]);

  // Callback refs to prevent realtime re-subscription loops
  const advanceSpeakingTurnRef = useRef<any>(null);
  const resolveVotingRef = useRef<any>(null);
  const resolveDefenseRef = useRef<any>(null);
  const resolveLiarScoreAndResultRef = useRef<any>(null);
  const applyStatePayloadRef = useRef<any>(null);

  // Helper to generate database safe room id
  const getFullRoomId = useCallback((rId: string, type: 'chat' | 'liar') => {
    return `${type}-${rId}`;
  }, []);

  // Handle mounting check to avoid Next.js hydration issues and verify environment credentials
  useEffect(() => {
    setIsMounted(true);
    const stored = localStorage.getItem('chat_username');
    if (stored) {
      setInputUsername(stored.substring(0, 10));
    }

    const isUrlPlaceholder = !process.env.NEXT_PUBLIC_SUPABASE_URL || 
                             process.env.NEXT_PUBLIC_SUPABASE_URL.includes('placeholder') ||
                             process.env.NEXT_PUBLIC_SUPABASE_URL === '';
    const isKeyPlaceholder = !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 
                             process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY.includes('placeholder') ||
                             process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY === '';
    setIsEnvMissing(isUrlPlaceholder || isKeyPlaceholder);
  }, []);

  // Update ref when username changes so real-time callbacks get the current value
  useEffect(() => {
    activeUsernameRef.current = username;
  }, [username]);

  // Smooth scroll to bottom
  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior });
    }
  }, []);

  // Web Audio API Synth Ping for premium notification sound
  const playPingSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const oscillator = audioCtx.createOscillator();
      const gainNode = audioCtx.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioCtx.destination);
      
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
      oscillator.frequency.exponentialRampToValueAtTime(880.00, audioCtx.currentTime + 0.08); // A5
      
      gainNode.gain.setValueAtTime(0.04, audioCtx.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
      
      oscillator.start();
      oscillator.stop(audioCtx.currentTime + 0.12);
    } catch (e) {
      console.warn('Web Audio Playback failed:', e);
    }
  }, [soundEnabled]);

  // Fetch initial chat logs for the specific room (with 5s query safety timeout)
  const fetchMessages = useCallback(async (activeRoomId: string) => {
    setLoading(true);
    const safetyTimeout = setTimeout(() => {
      setLoading(false);
      console.warn('Supabase query timed out after 5s. Loading screen bypassed.');
    }, 5000);

    try {
      const { data, error } = await supabase
        .from('chat_messages')
        .select('*')
        .eq('room_id', activeRoomId)
        .order('created_at', { ascending: true })
        .limit(100);

      clearTimeout(safetyTimeout);
      if (error) throw error;
      if (data) {
        setMessages(data);
      }
    } catch (err) {
      console.error('Error fetching chat history:', err);
    } finally {
      setLoading(false);
      setTimeout(() => scrollToBottom('auto'), 100);
    }
  }, [scrollToBottom]);

  // Unified State Applicator to update React states dynamically
  const applyStatePayload = useCallback((payload: any) => {
    if (payload.status !== undefined) setGameStatus(payload.status);
    if (payload.category !== undefined) setGameCategory(payload.category);
    if (payload.word !== undefined) setGameWord(payload.word);
    if (payload.liar !== undefined) setGameLiar(payload.liar);
    if (payload.round !== undefined) setRound(payload.round);
    if (payload.scores !== undefined) setScores(payload.scores);
    if (payload.speakingOrder !== undefined) setSpeakingOrder(payload.speakingOrder);
    if (payload.currentSpeakerIndex !== undefined) setCurrentSpeakerIndex(payload.currentSpeakerIndex);
    if (payload.timerSeconds !== undefined) setTimerSeconds(payload.timerSeconds);
    if (payload.votes !== undefined) setVotes(payload.votes);
    if (payload.nominatedPlayer !== undefined) setNominatedPlayer(payload.nominatedPlayer);
    if (payload.trialNumber !== undefined) setTrialNumber(payload.trialNumber);
    if (payload.defenseVotes !== undefined) setDefenseVotes(payload.defenseVotes);
    if (payload.descriptions !== undefined) setDescriptions(payload.descriptions);
    if (payload.caught !== undefined) setCaught(payload.caught);
  }, []);

  // System Database announcer insertion helper
  const insertSystemMessage = useCallback(async (text: string) => {
    if (!roomId) return;
    const fullRoomId = getFullRoomId(roomId, roomType);
    try {
      await supabase
        .from('chat_messages')
        .insert([
          {
            username: '📢 시스템',
            text: text,
            room_id: fullRoomId
          }
        ]);
    } catch (e) {
      console.error('System message insert failed:', e);
    }
  }, [roomId, roomType, getFullRoomId]);

  // Broadcast function
  const broadcastStateChange = useCallback((payload: any) => {
    if (chatChannelRef.current) {
      chatChannelRef.current.send({
        type: 'broadcast',
        event: 'state_change',
        payload: payload
      });
    }
    applyStatePayload(payload);
  }, [applyStatePayload]);

  // ==========================================
  // [Liar Game Python Aligned Engines]
  // ==========================================

  // Proceed to next step in turn-based speaking
  const advanceSpeakingTurn = useCallback((speaker: string, text: string) => {
    const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
    if (!isHost) return;

    const currentIdx = currentSpeakerIndexRef.current;
    const order = speakingOrderRef.current;
    const currentDescs = { ...descriptionsRef.current };
    
    // Append speech description
    if (!currentDescs[speaker]) currentDescs[speaker] = [];
    currentDescs[speaker].push(text);

    if (currentIdx < order.length - 1) {
      // Advance to next speaker
      const nextSpeaker = order[currentIdx + 1];
      broadcastStateChange({
        currentSpeakerIndex: currentIdx + 1,
        timerSeconds: 40,
        descriptions: currentDescs
      });
      insertSystemMessage(`👉 ${nextSpeaker}님의 발언 차례입니다! (40초)`);
    } else {
      // All speakers finished, advance to 지목 투표
      broadcastStateChange({
        status: 'voting',
        timerSeconds: 120,
        votes: {},
        descriptions: currentDescs
      });
      insertSystemMessage(`📢 모든 발언이 완료되었습니다. 2분간 지목 투표를 진행합니다.\n라이어라고 생각하는 사람 또는 '기권', '한 바퀴 더'에 투표해 주세요.`);
    }
  }, [broadcastStateChange, insertSystemMessage]);

  // Resolve 지목 투표 results
  const resolveVoting = useCallback(() => {
    const currentVotes = votesRef.current;
    const crew = onlineUsersRef.current.map(u => u.username);
    if (crew.length === 0) crew.push(activeUsernameRef.current);
    
    const voteCounts: Record<string, number> = {};
    let oneMoreCount = 0;
    let skipCount = 0;
    
    Object.values(currentVotes).forEach(target => {
      if (target === 'one_more') {
        oneMoreCount++;
      } else if (target === 'skip') {
        skipCount++;
      } else {
        voteCounts[target] = (voteCounts[target] || 0) + 1;
      }
    });

    // Output all vote counts to system log
    let resMsg = `🗳️ [지목 투표 결과 발표]\n`;
    crew.forEach(name => {
      resMsg += `- ${name}: ${voteCounts[name] || 0}표\n`;
    });
    resMsg += `- 기권: ${skipCount}표\n`;
    resMsg += `- 한 바퀴 더: ${oneMoreCount}표`;
    insertSystemMessage(resMsg);

    // Determine the top candidate
    const playerVotes = { ...voteCounts };
    const onemore_v = oneMoreCount;

    // If no votes at all and no one_more, nominate randomly (skip does not count)
    const hasAnyVote = Object.values(playerVotes).some(v => v > 0) || onemore_v > 0;
    
    if (!hasAnyVote) {
      const randomPicked = crew[Math.floor(Math.random() * crew.length)];
      const trial = trialNumberRef.current;
      broadcastStateChange({
        status: 'defense',
        nominatedPlayer: randomPicked,
        timerSeconds: 40,
        defenseVotes: {}
      });
      insertSystemMessage(`🎲 투표수가 없어 무작위로 [${randomPicked}]님이 단상에 오릅니다. 40초간 최후 변론을 진행하고 찬반 투표를 실시하세요. (현재 ${trial}차 지목)`);
      return;
    }

    const max_v = Math.max(...Object.values(playerVotes), onemore_v);
    const topCandidates: string[] = [];
    if (onemore_v === max_v) topCandidates.push('one_more');
    Object.entries(playerVotes).forEach(([name, count]) => {
      if (count === max_v) topCandidates.push(name);
    });

    const chosenTarget = topCandidates[Math.floor(Math.random() * topCandidates.length)];
    const isRandomlyPicked = topCandidates.length > 1;

    if (chosenTarget === 'one_more') {
      // 한 바퀴 더: reset speech and return to speaking
      broadcastStateChange({
        status: 'speaking',
        currentSpeakerIndex: 0,
        timerSeconds: 40,
        votes: {}
      });
      insertSystemMessage(`🔄 '한 바퀴 더'가 최다 득표를 얻었습니다! 기존 순서대로 발언을 한 번 더 진행합니다.`);
    } else {
      // Nominate player
      const trial = trialNumberRef.current;
      if (trial < 3) {
        broadcastStateChange({
          status: 'defense',
          nominatedPlayer: chosenTarget,
          timerSeconds: 40,
          defenseVotes: {}
        });
        const annPrefix = isRandomlyPicked ? `🎲 득표수가 같아 무작위로 [${chosenTarget}]님이 지목되었습니다.` : `👉 투표 결과 [${chosenTarget}]님이 지목되었습니다.`;
        insertSystemMessage(`${annPrefix} ${chosenTarget}님은 40초간 최후 변론을 진행하고, 생존자들은 찬반 투표(죽이기/살리기)를 완료해 주세요. (현재 ${trial}차 지목)`);
      } else {
        // 3차 투표: Force execution!
        insertSystemMessage(`🚨 3차 투표까지 도달하여 더 이상의 자비가 없습니다! [${chosenTarget}]님을 강제 처형합니다.`);
        revealIdentityAndSetCaught(chosenTarget);
      }
    }
  }, [broadcastStateChange, insertSystemMessage]);

  // Reveal Nominated Player's Identity
  const revealIdentityAndSetCaught = useCallback((target: string) => {
    const liar = gameLiarRef.current;
    const isLiar = target === liar;
    
    if (isLiar) {
      insertSystemMessage(`🚨 속보: [${target}]님은 진짜 [라이어]였습니다! 시민들의 승리가 눈앞입니다.`);
      broadcastStateChange({
        status: 'liar_guess',
        caught: true,
        timerSeconds: 120
      });
    } else {
      insertSystemMessage(`😇 속보: [${target}]님은 억울한 [시민]이었습니다! 라이어는 살아남았습니다.`);
      broadcastStateChange({
        caught: false
      });
      // Citizen executed: Liar wins immediately, skip to answer phase
      resolveLiarScoreAndResult(false);
    }
  }, [broadcastStateChange, insertSystemMessage]);

  // Resolve Defense trial results
  const resolveDefense = useCallback(() => {
    const currentDefVotes = defenseVotesRef.current;
    const nominated = nominatedPlayerRef.current;
    const trial = trialNumberRef.current;
    
    let killCount = 0;
    let spareCount = 0;
    
    Object.values(currentDefVotes).forEach(v => {
      if (v === 'kill') killCount++;
      if (v === 'spare') spareCount++;
    });

    const executed = killCount > spareCount;
    let resMsg = `🗳️ [처형 찬반 투표 결과: ${nominated}]\n- 죽이기: ${killCount}표 / 살리기: ${spareCount}표\n\n`;

    if (executed) {
      resMsg += `💥 과반수가 찬성하여 [${nominated}]님이 처형되었습니다!`;
      insertSystemMessage(resMsg);
      revealIdentityAndSetCaught(nominated);
    } else {
      resMsg += `🕊️ 살아남았습니다! 과반수의 찬성을 얻지 못해 처형이 무산되었습니다.`;
      if (trial < 3) {
        resMsg += `\n🚨 주의: 다음은 마지막 3차 투표입니다. 자비가 없습니다!`;
        insertSystemMessage(resMsg);
        broadcastStateChange({
          status: 'voting',
          timerSeconds: 120,
          trialNumber: trial + 1,
          votes: {}
        });
      } else {
        // Fallback guard, if somehow it was trial 3
        insertSystemMessage(resMsg + `\n🚨 3차 투표 한계에 도달해 강제 처형합니다.`);
        revealIdentityAndSetCaught(nominated);
      }
    }
  }, [broadcastStateChange, insertSystemMessage, revealIdentityAndSetCaught]);

  // Compute final scores and transition to result screen
  const resolveLiarScoreAndResult = useCallback((liarGuessedRight: boolean) => {
    const liar = gameLiarRef.current;
    const word = gameWordRef.current;
    const currentScores = { ...scoresRef.current };
    const liarCaught = caughtRef.current;

    let resMsg = `🔍 정답 공개: 제시어는 [${word}]였습니다!\n\n`;

    // 🏆 Python aligned high-risk high-return scoring calculation
    if (liarCaught) {
      if (!liarGuessedRight) {
        resMsg += `🎉 시민 완승! 라이어는 정답도 모르고 잡혔습니다! (라이어 -100점 / 시민 전원 +100점)`;
        currentScores[liar] = (currentScores[liar] || 0) - 100;
        onlineUsersRef.current.forEach(u => {
          if (u.username !== liar) {
            currentScores[u.username] = (currentScores[u.username] || 0) + 100;
          }
        });
      } else {
        resMsg += `😱 라이어 역전승! 검거되었지만 제시어를 눈치챘습니다! (라이어 +100점 / 시민 0점)`;
        currentScores[liar] = (currentScores[liar] || 0) + 100;
      }
    } else {
      if (!liarGuessedRight) {
        resMsg += `♻️ 라이어 생존! 하지만 정답은 몰랐네요! (라이어 +100점 / 시민 0점)`;
        currentScores[liar] = (currentScores[liar] || 0) + 100;
      } else {
        resMsg += `😈 라이어 완승! 완벽하게 속이고 정답까지 맞혔습니다! (라이어 +200점 / 시민 0점)`;
        currentScores[liar] = (currentScores[liar] || 0) + 200;
      }
    }

    insertSystemMessage(resMsg);

    broadcastStateChange({
      status: 'result',
      scores: currentScores,
      timerSeconds: 0
    });

    // Auto proceed to next round or final podium after 7 seconds
    setTimeout(() => {
      const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
      if (!isHost) return;

      const currentRound = roundRef.current;
      if (currentRound < 3) {
        insertSystemMessage(`➡️ ROUND ${currentRound} 종료. 잠시 후 다음 라운드로 이동합니다.`);
        setTimeout(() => {
          handleNextRoundStart(currentRound + 1, currentScores);
        }, 3000);
      } else {
        broadcastStateChange({
          status: 'final_scoreboard'
        });
        insertSystemMessage(`🏁 3라운드 게임 종료 - 최종 우승자 발표!`);
      }
    }, 7000);
  }, [broadcastStateChange, insertSystemMessage]);

  // Start next round automatically
  const handleNextRoundStart = async (nextRound: number, targetScores: Record<string, number>) => {
    if (!chatChannelRef.current || !roomId) return;

    const crewNames = onlineUsersRef.current.map(u => u.username);
    const shuffledOrder = [...crewNames].sort(() => Math.random() - 0.5);
    
    const categories = Object.keys(LIAR_WORDS);
    const randomCategory = categories[Math.floor(Math.random() * categories.length)];
    const words = LIAR_WORDS[randomCategory];
    const randomWord = words[Math.floor(Math.random() * words.length)];
    const randomLiar = crewNames[Math.floor(Math.random() * crewNames.length)];
    const fullRoomId = getFullRoomId(roomId, roomType);

    try {
      await supabase
        .from('chat_messages')
        .insert([
          {
            username: '📢 시스템',
            text: `🎮 [라이어 게임 - 라운드 ${nextRound}] 시작!\n카테고리: [${randomCategory}]\n\n순서대로 40초간 설명해 주세요.\n첫 발언 주자: ${shuffledOrder[0]}님`,
            room_id: fullRoomId
          }
        ]);

      broadcastStateChange({
        status: 'speaking',
        category: randomCategory,
        word: randomWord,
        liar: randomLiar,
        round: nextRound,
        scores: targetScores,
        speakingOrder: shuffledOrder,
        currentSpeakerIndex: 0,
        timerSeconds: 40,
        votes: {},
        defenseVotes: {},
        trialNumber: 1,
        nominatedPlayer: '',
        descriptions: { [randomLiar]: [] },
        caught: false
      });
    } catch (e) {
      console.error('Failed to trigger next round:', e);
    }
  };

  // Reset Game and return to Waiting Lobby
  const handleResetGame = () => {
    broadcastStateChange({
      status: 'waiting',
      category: '',
      word: '',
      liar: '',
      round: 1,
      scores: {},
      speakingOrder: [],
      currentSpeakerIndex: 0,
      timerSeconds: 0,
      votes: {},
      nominatedPlayer: '',
      trialNumber: 1,
      defenseVotes: {},
      descriptions: {},
      caught: false
    });
  };

  // Timer expiry event handler
  const handleTimerExpiry = useCallback(() => {
    const status = gameStatusRef.current;
    
    if (status === 'speaking') {
      const idx = currentSpeakerIndexRef.current;
      const order = speakingOrderRef.current;
      const activeSpeaker = order[idx];
      
      insertSystemMessage(`⏰ [${activeSpeaker}]님 시간 초과! (시간 초과 기록 저장)`);
      advanceSpeakingTurn(activeSpeaker, '(시간 초과)');
    } else if (status === 'voting') {
      resolveVoting();
    } else if (status === 'defense') {
      resolveDefense();
    } else if (status === 'liar_guess') {
      resolveLiarScoreAndResult(false);
    }
  }, [insertSystemMessage, advanceSpeakingTurn, resolveVoting, resolveDefense, resolveLiarScoreAndResult]);

  // Sync callbacks with refs
  useEffect(() => { advanceSpeakingTurnRef.current = advanceSpeakingTurn; }, [advanceSpeakingTurn]);
  useEffect(() => { resolveVotingRef.current = resolveVoting; }, [resolveVoting]);
  useEffect(() => { resolveDefenseRef.current = resolveDefense; }, [resolveDefense]);
  useEffect(() => { resolveLiarScoreAndResultRef.current = resolveLiarScoreAndResult; }, [resolveLiarScoreAndResult]);
  useEffect(() => { applyStatePayloadRef.current = applyStatePayload; }, [applyStatePayload]);

  // Host-driven interval timer loop
  useEffect(() => {
    if (!roomId || !username || gameStatus === 'waiting' || gameStatus === 'final_scoreboard' || gameStatus === 'result') return;

    const isHost = onlineUsers.length > 0 && onlineUsers[0].username === username;
    if (!isHost) return;

    const interval = setInterval(() => {
      const currentSec = timerSecondsRef.current;
      if (currentSec > 0) {
        const nextSec = currentSec - 1;
        setTimerSeconds(nextSec);
        
        if (chatChannelRef.current) {
          chatChannelRef.current.send({
            type: 'broadcast',
            event: 'timer_tick',
            payload: { seconds: nextSec }
          });
        }
      } else {
        handleTimerExpiry();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [gameStatus, roomId, username, onlineUsers, handleTimerExpiry]);

  // ==========================================
  // [Client Trigger Submissions]
  // ==========================================

  // Submit normal 지목 vote
  const handleSubmitVote = (target: string) => {
    if (!roomId || !username || !chatChannelRef.current) return;
    
    chatChannelRef.current.send({
      type: 'broadcast',
      event: 'submit_vote',
      payload: { voter: username, target: target }
    });
    
    setVotes(prev => ({ ...prev, [username]: target }));
  };

  // Submit defense 찬반 vote
  const handleSubmitDefenseVote = (vote: 'kill' | 'spare') => {
    if (!roomId || !username || !chatChannelRef.current) return;
    
    chatChannelRef.current.send({
      type: 'broadcast',
      event: 'submit_defense_vote',
      payload: { voter: username, vote: vote }
    });
    
    setDefenseVotes(prev => ({ ...prev, [username]: vote }));
  };

  // Submit Liar guess word
  const handleLiarGuessSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanGuess = liarGuessText.trim();
    if (!cleanGuess || !chatChannelRef.current) return;
    
    setLiarGuessText('');
    
    const cleanWord = gameWord.replace(/\s+/g, '');
    const isCorrect = cleanGuess.replace(/\s+/g, '') === cleanWord;
    
    chatChannelRef.current.send({
      type: 'broadcast',
      event: 'liar_guess_result',
      payload: { correct: isCorrect, guess: cleanGuess }
    });
  };

  // Start round 1 game
  const handleStartGame = async () => {
    if (!chatChannelRef.current || !roomId) return;

    const crewNames = onlineUsers.map(u => u.username);
    if (crewNames.length < 3) {
      alert('최소 3명 이상의 크루원이 접속해야 게임을 시작할 수 있습니다.');
      return;
    }

    const shuffledOrder = [...crewNames].sort(() => Math.random() - 0.5);
    const categories = Object.keys(LIAR_WORDS);
    const randomCategory = categories[Math.floor(Math.random() * categories.length)];
    const words = LIAR_WORDS[randomCategory];
    const randomWord = words[Math.floor(Math.random() * words.length)];
    const randomLiar = crewNames[Math.floor(Math.random() * crewNames.length)];
    const fullRoomId = getFullRoomId(roomId, roomType);

    try {
      // 1. Wipe previous chat history in this room to avoid displaying old game logs
      await supabase.from('chat_messages').delete().eq('room_id', fullRoomId);
      setMessages([]);

      // 2. Insert fresh start system announcement
      await supabase
        .from('chat_messages')
        .insert([
          {
            username: '📢 시스템',
            text: `🎮 [라이어 게임 - 라운드 1] 시작!\n카테고리: [${randomCategory}]\n\n순서대로 40초간 설명해 주세요.\n첫 발언 주자: ${shuffledOrder[0]}님`,
            room_id: fullRoomId
          }
        ]);

      broadcastStateChange({
        status: 'speaking',
        category: randomCategory,
        word: randomWord,
        liar: randomLiar,
        round: 1,
        scores: {},
        speakingOrder: shuffledOrder,
        currentSpeakerIndex: 0,
        timerSeconds: 40,
        votes: {},
        defenseVotes: {},
        trialNumber: 1,
        nominatedPlayer: '',
        descriptions: { [randomLiar]: [] },
        caught: false
      });
    } catch (err) {
      console.error('Failed to start game:', err);
      alert('게임 시작 중 오류가 발생했습니다.');
    }
  };

  // Send normal chat message / intercepts for turn based speech
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanText = inputText.trim();
    if (!cleanText || !roomId) return;

    setSending(true);
    setInputText('');

    const fullRoomId = getFullRoomId(roomId, roomType);

    if (gameStatus === 'speaking') {
      const activeSpeaker = speakingOrder[currentSpeakerIndex];
      if (activeSpeaker === username) {
        if (chatChannelRef.current) {
          chatChannelRef.current.send({
            type: 'broadcast',
            event: 'submit_speech',
            payload: { speaker: username, text: cleanText }
          });
        }
      }
    }

    try {
      const { error } = await supabase
        .from('chat_messages')
        .insert([
          {
            username: username,
            text: cleanText,
            room_id: fullRoomId
          }
        ]);

      if (error) throw error;
    } catch (err) {
      console.error('Failed to send message:', err);
      setInputText(cleanText);
    } finally {
      setSending(false);
    }
  };

  // Exit Room
  const handleExit = () => {
    if (chatChannelRef.current) {
      supabase.removeChannel(chatChannelRef.current);
      chatChannelRef.current = null;
    }
    setUsername('');
    setRoomId('');
    setMessages([]);
    setOnlineUsers([]);
    setGameStatus('waiting');
  };

  // Subscribe to Realtime channels
  useEffect(() => {
    if (!username || !roomId) return;

    const fullRoomId = getFullRoomId(roomId, roomType);
    fetchMessages(fullRoomId);

    const channel = supabase.channel(`chat_room_${fullRoomId}`, {
      config: {
        presence: {
          key: username,
        },
        broadcast: {
          self: true,
        },
      },
    })
      .on(
        'postgres_changes',
        { 
          event: 'INSERT', 
          schema: 'public', 
          table: 'chat_messages',
          filter: `room_id=eq.${fullRoomId}`
        },
        (payload) => {
          const newMsg = payload.new as Message;
          setMessages((prev) => {
            if (prev.some((m) => m.id === newMsg.id)) return prev;
            return [...prev, newMsg];
          });
          
          setTimeout(() => scrollToBottom('smooth'), 50);
          
          if (newMsg.username !== activeUsernameRef.current) {
            playPingSound();
          }
        }
      )
      .on('broadcast', { event: 'state_change' }, ({ payload }) => {
        applyStatePayloadRef.current?.(payload);
      })
      .on('broadcast', { event: 'request_state' }, () => {
        if (gameStatusRef.current !== 'waiting' && chatChannelRef.current) {
          chatChannelRef.current.send({
            type: 'broadcast',
            event: 'sync_state',
            payload: {
              status: gameStatusRef.current,
              category: gameCategoryRef.current,
              word: gameWordRef.current,
              liar: gameLiarRef.current,
              round: roundRef.current,
              scores: scoresRef.current,
              speakingOrder: speakingOrderRef.current,
              currentSpeakerIndex: currentSpeakerIndexRef.current,
              timerSeconds: timerSecondsRef.current,
              votes: votesRef.current,
              nominatedPlayer: nominatedPlayerRef.current,
              trialNumber: trialNumberRef.current,
              defenseVotes: defenseVotesRef.current,
              descriptions: descriptionsRef.current,
              caught: caughtRef.current
            }
          });
        }
      })
      .on('broadcast', { event: 'sync_state' }, ({ payload }) => {
        applyStatePayloadRef.current?.(payload);
      })
      .on('broadcast', { event: 'update_votes' }, ({ payload }) => {
        setVotes(payload.votes);
      })
      .on('broadcast', { event: 'update_defense_votes' }, ({ payload }) => {
        setDefenseVotes(payload.defenseVotes);
      })
      .on('broadcast', { event: 'submit_speech' }, ({ payload }) => {
        const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
        if (isHost) {
          advanceSpeakingTurnRef.current?.(payload.speaker, payload.text);
        }
      })
      .on('broadcast', { event: 'timer_tick' }, ({ payload }) => {
        setTimerSeconds(payload.seconds);
      })
      .on('broadcast', { event: 'submit_vote' }, ({ payload }) => {
        const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
        if (!isHost) return;
        
        const newVotes: Record<string, string> = { ...votesRef.current, [payload.voter]: payload.target };
        setVotes(newVotes);
        
        channel.send({
          type: 'broadcast',
          event: 'update_votes',
          payload: { votes: newVotes }
        });
        
        const crewNames = onlineUsersRef.current.map(u => u.username);
        const hasEveryoneVoted = crewNames.every(name => newVotes[name] !== undefined);
        if (hasEveryoneVoted) {
          resolveVotingRef.current?.();
        }
      })
      .on('broadcast', { event: 'submit_defense_vote' }, ({ payload }) => {
        const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
        if (!isHost) return;
        
        const newDefVotes: Record<string, 'kill' | 'spare'> = { ...defenseVotesRef.current, [payload.voter]: payload.vote };
        setDefenseVotes(newDefVotes);
        
        channel.send({
          type: 'broadcast',
          event: 'update_defense_votes',
          payload: { defenseVotes: newDefVotes }
        });
        
        const nominated = nominatedPlayerRef.current;
        const crewNames = onlineUsersRef.current.map(u => u.username).filter(name => name !== nominated);
        const hasEveryoneVoted = crewNames.every(name => newDefVotes[name] !== undefined);
        if (hasEveryoneVoted) {
          resolveDefenseRef.current?.();
        }
      })
      .on('broadcast', { event: 'liar_guess_result' }, ({ payload }) => {
        const isHost = onlineUsersRef.current.length > 0 && onlineUsersRef.current[0].username === activeUsernameRef.current;
        if (!isHost) return;
        
        resolveLiarScoreAndResultRef.current?.(payload.correct);
      })
      .on('presence', { event: 'sync' }, () => {
        const state = channel.presenceState();
        const activeCrew: OnlineUser[] = Object.keys(state).map((key) => {
          const presences = state[key] as unknown as Array<{ online_at: string; username: string }>;
          return {
            username: presences[0]?.username || key,
            online_at: presences[0]?.online_at || new Date().toISOString(),
          };
        });
        
        activeCrew.sort((a, b) => new Date(a.online_at).getTime() - new Date(b.online_at).getTime());
        setOnlineUsers(activeCrew);
      })
      .subscribe(async (status) => {
        if (status === 'SUBSCRIBED') {
          try {
            await channel.track({
              online_at: new Date().toISOString(),
              username: username,
            });
          } catch (e) {
            console.error('Failed to track user presence:', e);
          }

          setTimeout(() => {
            if (chatChannelRef.current) {
              chatChannelRef.current.send({
                type: 'broadcast',
                event: 'request_state',
                payload: {}
              });
            }
          }, 1000);
        }
      });

    chatChannelRef.current = channel;

    return () => {
      supabase.removeChannel(channel);
      chatChannelRef.current = null;
    };
  }, [username, roomId, roomType, fetchMessages, scrollToBottom, playPingSound, getFullRoomId]);

  // Copy Room Code
  const handleCopyCode = () => {
    if (!roomId) return;
    navigator.clipboard.writeText(roomId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Handle Login
  const handleLoginSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanUsername = inputUsername.trim();
    if (!cleanUsername) {
      alert('닉네임을 입력해 주세요.');
      return;
    }
    if (cleanUsername.length > 10) {
      alert('닉네임은 최대 10자까지만 입력 가능합니다.');
      return;
    }

    localStorage.setItem('chat_username', cleanUsername);

    let targetRoomId = '';
    if (roomMode === 'create') {
      targetRoomId = String(Math.floor(10000 + Math.random() * 90000));
    } else {
      const cleanRoomId = inputRoomId.trim();
      if (!cleanRoomId || cleanRoomId.length !== 5 || isNaN(Number(cleanRoomId))) {
        alert('올바른 5자리 방 번호를 입력해 주세요.');
        return;
      }
      targetRoomId = cleanRoomId;
    }

    setUsername(cleanUsername);
    setRoomId(targetRoomId);
  };

  // Format timer text
  const formatTimerText = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m < 10 ? '0' + m : m}:${s < 10 ? '0' + s : s}`;
  };

  // Format date helper
  const formatTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
    } catch (e) {
      return '';
    }
  };

  // Hydration safety check
  if (!isMounted) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-stone-50 text-stone-800">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-stone-200 border-t-rose-500"></div>
          <span className="text-sm text-stone-500 font-medium tracking-wide">로딩 중...</span>
        </div>
      </div>
    );
  }

  // 1. Entry / Room Setup Screen (Cozy Cream Theme)
  if (!username || !roomId) {
    return (
      <div className="flex flex-1 min-h-screen flex-col items-center justify-center bg-amber-50/50 p-4 relative overflow-hidden">
        {/* Cozy Soft Glowing Blobs */}
        <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-80 h-80 rounded-full bg-rose-200/40 blur-3xl"></div>
        <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-80 h-80 rounded-full bg-amber-200/40 blur-3xl"></div>

        <div className="w-full max-w-md relative z-10">
          {/* Logo / Header */}
          <div className="text-center mb-8 flex flex-col items-center gap-2">
            <div className="h-12 w-12 rounded-2xl bg-gradient-to-tr from-rose-400 to-amber-300 flex items-center justify-center shadow-md">
              <MessageSquare className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-3xl font-black tracking-tight text-stone-800 mt-4">
              JUJE Multi Lounge
            </h1>
            <p className="text-sm text-stone-500 font-bold">
              아기자기한 실시간 소통 놀이터 🏡
            </p>
          </div>

          {/* Form Card */}
          <div className="bg-white/90 backdrop-blur-xl border border-stone-200/80 rounded-3xl overflow-hidden shadow-xl">
            {/* Room Mode Toggle Tabs */}
            <div className="flex border-b border-stone-200 bg-stone-50/50">
              <button
                type="button"
                onClick={() => setRoomMode('join')}
                className={`flex-1 py-4 text-sm font-bold flex items-center justify-center gap-2 transition-all ${
                  roomMode === 'join' 
                    ? 'text-stone-800 border-b-2 border-rose-400 bg-white' 
                    : 'text-stone-400 hover:text-stone-600'
                }`}
              >
                <LogIn className="h-4 w-4 text-rose-400" />
                방 입장하기
              </button>
              <button
                type="button"
                onClick={() => setRoomMode('create')}
                className={`flex-1 py-4 text-sm font-bold flex items-center justify-center gap-2 transition-all ${
                  roomMode === 'create' 
                    ? 'text-stone-800 border-b-2 border-rose-400 bg-white' 
                    : 'text-stone-400 hover:text-stone-600'
                }`}
              >
                <PlusCircle className="h-4 w-4 text-rose-400" />
                방 만들기
              </button>
            </div>

            <form onSubmit={handleLoginSubmit} className="p-8 space-y-6">
              {isEnvMissing && (
                <div className="bg-amber-500/10 border border-amber-500/20 rounded-2xl p-4 animate-pulse">
                  <span className="text-xs font-bold text-amber-600 block mb-1">⚠️ Supabase 설정 누락 감지</span>
                  <p className="text-[11px] text-stone-500 leading-relaxed font-medium">
                    `.env.local` 또는 Vercel 환경 변수가 구성되지 않았습니다. 대기실 입장 후 채팅 전송 및 실시간 접속자 추적이 동작하지 않습니다.
                  </p>
                </div>
              )}

              {/* Username Input */}
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label htmlFor="username-input" className="block text-xs font-bold uppercase tracking-wider text-stone-500">
                    크루원 닉네임
                  </label>
                  <span className="text-[10px] text-stone-400 font-bold">{inputUsername.length}/10자</span>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-stone-400">
                    <User className="h-5 w-5" />
                  </div>
                  <input
                    id="username-input"
                    type="text"
                    required
                    maxLength={10}
                    placeholder="닉네임을 입력하세요 (최대 10자)"
                    value={inputUsername}
                    onChange={(e) => setInputUsername(e.target.value)}
                    className="block w-full pl-11 pr-4 py-3.5 bg-stone-50/50 border border-stone-200 rounded-2xl text-stone-800 placeholder-stone-400 focus:outline-none focus:border-rose-400 focus:ring-2 focus:ring-rose-400/15 transition-all font-medium text-sm"
                  />
                </div>
              </div>

              {/* Room ID Input */}
              {roomMode === 'join' && (
                <div className="animate-in fade-in slide-in-from-top-2 duration-200">
                  <label htmlFor="room-input" className="block text-xs font-bold uppercase tracking-wider text-stone-500 mb-2">
                    입장할 방 번호 (5자리)
                  </label>
                  <input
                    id="room-input"
                    type="text"
                    required={roomMode === 'join'}
                    pattern="[0-9]{5}"
                    maxLength={5}
                    placeholder="예: 12345"
                    value={inputRoomId}
                    onChange={(e) => {
                      const val = e.target.value.replace(/[^0-9]/g, '');
                      setInputRoomId(val);
                    }}
                    className="block w-full px-4 py-3.5 bg-stone-50/50 border border-stone-200 rounded-2xl text-stone-800 placeholder-stone-400 focus:outline-none focus:border-rose-400 focus:ring-2 focus:ring-rose-400/15 transition-all font-bold text-center tracking-widest text-lg font-mono"
                  />
                </div>
              )}

              {/* Room Type Toggle Buttons */}
              <div className="space-y-2">
                <span className="block text-xs font-bold uppercase tracking-wider text-stone-500">
                  방 모드 선택
                </span>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setRoomType('chat')}
                    className={`py-3 px-4 rounded-2xl border text-xs font-bold transition-all flex flex-col items-center justify-center gap-1.5 ${
                      roomType === 'chat'
                        ? 'bg-rose-400 border-rose-300 text-white shadow-md'
                        : 'bg-stone-50 border-stone-200 text-stone-500 hover:text-stone-700'
                    }`}
                  >
                    <MessageSquare className="h-4.5 w-4.5" />
                    일반 채팅방
                  </button>
                  <button
                    type="button"
                    onClick={() => setRoomType('liar')}
                    className={`py-3 px-4 rounded-2xl border text-xs font-bold transition-all flex flex-col items-center justify-center gap-1.5 ${
                      roomType === 'liar'
                        ? 'bg-rose-400 border-rose-300 text-white shadow-md'
                        : 'bg-stone-50 border-stone-200 text-stone-500 hover:text-stone-700'
                    }`}
                  >
                    <Sparkles className="h-4.5 w-4.5" />
                    라이어 게임방
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={!inputUsername.trim() || (roomMode === 'join' && inputRoomId.length !== 5)}
                className="w-full py-4 px-6 rounded-full bg-gradient-to-r from-rose-400 to-orange-400 hover:from-rose-500 hover:to-orange-500 text-white font-bold text-base shadow-md hover:-translate-y-0.5 disabled:opacity-50 disabled:pointer-events-none transition-all flex items-center justify-center gap-2 group"
              >
                {roomMode === 'create' ? '방 개설 및 입장하기' : '방 입장하기'}
                <ChevronRight className="h-5 w-5 group-hover:translate-x-0.5 transition-transform" />
              </button>

              {roomType === 'liar' && (
                <div className="mt-4 pt-4 border-t border-stone-200 animate-in fade-in duration-200">
                  <button
                    type="button"
                    onClick={() => setShowRulesGuide(!showRulesGuide)}
                    className="w-full text-xs font-bold text-rose-500 hover:text-rose-600 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <HelpCircle className="h-4 w-4" />
                    <span>🎯 라이어 게임 규칙 및 방법 보기</span>
                    <span className={`transform transition-transform duration-200 ${showRulesGuide ? 'rotate-180' : ''}`}>▼</span>
                  </button>

                  {showRulesGuide && (
                    <div className="mt-4 text-xs text-stone-600 space-y-3.5 bg-stone-50 p-4 rounded-2xl border border-stone-200 max-h-60 overflow-y-auto text-left animate-in fade-in slide-in-from-top-2 duration-200">
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">🎮 1. 게임 개요 (3라운드 승점제)</span>
                        <p className="leading-relaxed">총 3라운드를 번갈아 진행해 점수가 가장 높은 사람이 최종 우승합니다!</p>
                      </div>
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">🎭 2. 역할 및 정보 배분</span>
                        <p className="leading-relaxed">시민들은 카테고리와 정확한 제시어를 받으며, 라이어는 카테고리 정보만 받습니다.</p>
                      </div>
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">🗣️ 3. 눈치싸움! 발언 페이즈 (40초)</span>
                        <p className="leading-relaxed">순서대로 40초씩 힌트를 설명합니다. 시민은 적절히 숨겨 말하고, 라이어는 뻔뻔히 아는 척 연기하세요.</p>
                      </div>
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">🗳️ 4. 지목 투표 & 한 바퀴 더 (2분)</span>
                        <p className="leading-relaxed">대화 후 2분간 투표합니다. 힌트 부족 시 [🔄 한 바퀴 더]에 투표하여 발언을 연장할 수 있습니다.</p>
                      </div>
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">⚖️ 5. 최후 변론 & 찬반 투표 (최대 3차)</span>
                        <p className="leading-relaxed">지목된 자는 40초간 최후 변론을 하며, 생존자들은 [죽이기 🔪] vs [살리기 🕊️] 찬반 투표를 합니다. 3차 투표 시 자동 강제 처형됩니다.</p>
                      </div>
                      <div>
                        <span className="font-bold text-stone-800 block mb-1">🔄 6. 라이어 역전 찬스 (2분)</span>
                        <p className="leading-relaxed">처형된 라이어는 2분간 정답 제시어를 입력할 기회를 얻습니다. 맞출 경우 라이어가 역전 승리합니다!</p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </form>
          </div>
        </div>
      </div>
    );
  }

  // Cozy dashboard screen layout
  const isHost = onlineUsers.length > 0 && onlineUsers[0].username === username;

  return (
    <div className="flex w-full h-screen flex-col bg-amber-50/20 text-stone-800 font-sans overflow-hidden">
      {/* Top Header */}
      <header className="h-16 px-4 md:px-6 bg-white/80 backdrop-blur-md border-b border-stone-200/80 flex items-center justify-between z-10 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-rose-400 to-orange-400 flex items-center justify-center shadow-sm">
            <MessageSquare className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <span className="font-extrabold text-stone-800 text-sm md:text-base">
              {roomType === 'liar' ? 'JUJE 라이어 게임룸 🕵️' : 'JUJE 크루 대기실 🏡'}
            </span>
          </div>
          
          {/* Room Code Badge */}
          <div className="flex items-center gap-1.5 pl-2.5 pr-1 py-1 rounded-full bg-stone-100/80 border border-stone-200/60">
            <span className="text-xs text-stone-500 font-bold">방번호:</span>
            <span className="text-xs text-stone-800 font-black font-mono tracking-widest bg-white px-2.5 py-0.5 rounded-full border border-stone-200">{roomId}</span>
            
            {/* Copy Button */}
            <button
              onClick={handleCopyCode}
              className={`p-1.5 rounded-full transition-all active:scale-90 ${
                copied ? 'bg-emerald-100 text-emerald-600' : 'bg-transparent text-stone-400 hover:text-stone-600'
              }`}
              title="방 번호 복사"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          </div>

          {/* Live Indicator */}
          <div className="flex items-center gap-1.5 bg-rose-50 border border-rose-100 px-2 py-0.5 rounded-full">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-500 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-rose-500"></span>
            </span>
            <span className="text-[10px] font-bold text-rose-600 flex items-center gap-1 font-mono">
              {onlineUsers.length}/12명
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Sound Toggle */}
          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={`p-2 rounded-xl border transition-all ${
              soundEnabled 
                ? 'bg-stone-100 border-stone-200 text-rose-500 hover:bg-stone-200/50' 
                : 'bg-stone-50 border-stone-200 text-stone-400 hover:bg-stone-100'
            }`}
            title={soundEnabled ? "알림음 켜짐" : "알림음 꺼짐"}
          >
            {soundEnabled ? <Volume2 className="h-5 w-5" /> : <VolumeX className="h-5 w-5" />}
          </button>

          {/* Exit Room */}
          <button
            onClick={handleExit}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-stone-100 border border-stone-200 text-stone-600 hover:bg-stone-200 hover:text-stone-800 transition-all text-xs font-bold"
          >
            <LogOut className="h-4 w-4" />
            <span>나가기</span>
          </button>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex flex-1 flex-row overflow-hidden relative">
        
        {/* Sidebar: Online Crew Members */}
        <aside className="w-64 bg-stone-100/80 border-r border-stone-200/80 hidden md:flex flex-col flex-shrink-0">
          <div className="p-4 border-b border-stone-200 flex items-center gap-2 text-stone-600">
            <Users className="h-4 w-4 text-rose-500" />
            <span className="text-xs font-bold uppercase tracking-wider">접속 중인 크루</span>
            <span className="ml-auto text-[10px] bg-stone-200 text-stone-600 px-1.5 py-0.5 rounded-md font-bold">
              {onlineUsers.length}명
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {onlineUsers.map((user) => {
              const userScore = scores[user.username] || 0;
              return (
                <div 
                  key={user.username} 
                  className={`flex items-center gap-3 px-3 py-2 rounded-xl transition-all ${
                    user.username === username 
                      ? 'bg-amber-100/60 border border-amber-200/60 text-stone-800 shadow-sm' 
                      : 'text-stone-600 hover:bg-stone-200/50'
                  }`}
                >
                  <div className={`h-8 w-8 rounded-lg bg-gradient-to-br ${getAvatarGradient(user.username)} flex items-center justify-center text-xs font-bold text-white shadow-sm flex-shrink-0`}>
                    {getInitials(user.username)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-center gap-1">
                      <p className="text-sm font-bold truncate leading-none mb-0.5">
                        {user.username}
                      </p>
                      {roomType === 'liar' && (
                        <span className="text-[10px] text-amber-600 font-extrabold font-mono">
                          {userScore}점
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-stone-400 flex items-center gap-1 font-medium">
                      {user.username === username ? '나' : '접속 중'}
                      <span className="h-1 w-1 rounded-full bg-emerald-500"></span>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="p-4 border-t border-stone-200/80 bg-stone-50/50 flex flex-col gap-2 mt-auto">
            {roomType === 'liar' && gameStatus !== 'waiting' && gameStatus !== 'final_scoreboard' && (
              <div className="mb-2 p-3.5 rounded-2xl border text-xs font-bold bg-white border-stone-200 shadow-sm">
                <div className="flex justify-between items-center mb-1 text-[10px] text-stone-400 font-bold tracking-wider uppercase">
                  <span>🕵️ 나의 역할 카드</span>
                  <span>R{round}</span>
                </div>
                <div className={`mt-1.5 p-2 rounded-xl text-center font-bold ${
                  gameLiar === username 
                    ? 'bg-rose-50 text-rose-500 border border-rose-200' 
                    : 'bg-teal-50 text-teal-500 border border-teal-200'
                }`}>
                  {gameLiar === username ? '라이어 (Liar)' : '시민 (Citizen)'}
                </div>
                {gameLiar !== username && (
                  <div className="mt-2 pt-2 border-t border-stone-100 flex justify-between items-center text-[10px]">
                    <span className="text-stone-400 font-bold">제시어:</span>
                    <span className="text-rose-500 font-black text-[11px]">{gameWord}</span>
                  </div>
                )}
              </div>
            )}
            {roomType === 'liar' && (
              <div className="flex items-center gap-2 text-xs text-rose-500 font-bold">
                <span>👑 방장: {onlineUsers[0]?.username || '없음'}</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-xs text-stone-400 font-bold">
              <Wifi className="h-3 w-3 text-stone-500" />
              <span>실시간 동기화 상태: 안정</span>
            </div>
          </div>
        </aside>

        {/* Chat / Message Area */}
        <main className="flex-1 flex flex-col bg-stone-50/40 relative overflow-hidden">
          
          {/* ==========================================
              [Liar Game Sticky Top Panel UI]
              ========================================== */}
          {roomType === 'liar' && (
            <div className="flex-shrink-0 p-4 border-b border-stone-200 bg-white/80 backdrop-blur-md">
              <div className="max-w-4xl mx-auto w-full">
                <div className="bg-white border border-stone-200/80 rounded-3xl p-6 shadow-md relative overflow-hidden animate-in fade-in duration-300">
                  <div className="absolute top-0 right-0 w-32 h-32 rounded-full bg-rose-200/10 blur-2xl pointer-events-none"></div>

                  {/* Speech records drawer toggle */}
                  {gameStatus !== 'waiting' && (
                    <div className="absolute top-4 right-4 z-20">
                      <button
                        onClick={() => setShowSpeechHistory(!showSpeechHistory)}
                        className="py-1.5 px-3 rounded-xl bg-stone-100 border border-stone-200 hover:border-stone-300 text-stone-600 hover:text-stone-800 transition-all text-xs font-bold flex items-center gap-1.5"
                      >
                        <List className="h-3.5 w-3.5 text-rose-500" />
                        발언 기록 목록
                      </button>
                    </div>
                  )}

                  {/* Speech history slide-down list */}
                  {showSpeechHistory && gameStatus !== 'waiting' && (
                    <div className="bg-stone-50 border border-stone-200 rounded-2xl p-4 mb-4 space-y-2 max-h-52 overflow-y-auto animate-in slide-in-from-top-2 duration-200">
                      <h4 className="text-xs font-bold text-rose-500 border-b border-stone-200 pb-1.5 flex items-center gap-1">
                        📢 라운드 {round} 발언 기록 목록
                      </h4>
                      {speakingOrder.map((name) => {
                        const list = descriptions[name] || [];
                        const cleaned = list.filter(d => !(d === '(시간 초과)' && list.length > 1));
                        return (
                          <div key={name} className="text-xs border-b border-stone-200 pb-2 last:border-0 last:pb-0">
                            <span className="font-extrabold text-stone-700 block mb-1">👤 {name}:</span>
                            {cleaned.length > 0 ? (
                              cleaned.map((txt, idx) => (
                                <p key={idx} className="text-stone-500 pl-2 leading-relaxed">
                                  • {txt}
                                </p>
                              ))
                            ) : (
                              <p className="text-stone-400 pl-2 italic">(기록 없음)</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* State 1: WAITING FOR START */}
                  {gameStatus === 'waiting' && (
                    <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                      <div className="flex items-center gap-4">
                        <div className="h-12 w-12 rounded-2xl bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-500 animate-pulse">
                          <Sparkles className="h-6 w-6" />
                        </div>
                        <div>
                          <h2 className="text-base font-black text-stone-800 flex items-center gap-2">
                            <span>🎮 실시간 라이어 게임 대기실</span>
                            <span className="text-xs bg-rose-100 text-rose-500 border border-rose-200 px-2 py-0.5 rounded-full font-mono">LOBBY</span>
                          </h2>
                          <p className="text-xs text-stone-500 mt-1.5 leading-relaxed">
                            게임 대기 중입니다. 참가자들이 모두 모이면 시작해 주세요.<br />
                            (라이어 게임은 최소 3명의 참가자가 필요합니다.)
                          </p>
                        </div>
                      </div>
                      {isHost ? (
                        <button
                          onClick={handleStartGame}
                          disabled={onlineUsers.length < 3}
                          className="w-full md:w-auto py-3.5 px-6 rounded-full bg-gradient-to-r from-rose-400 to-orange-400 hover:from-rose-500 hover:to-orange-500 text-white text-sm font-bold shadow-md hover:-translate-y-0.5 active:scale-95 transition-all flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Play className="h-4 w-4 fill-white" />
                          게임 시작
                        </button>
                      ) : (
                        <div className="text-xs text-stone-500 font-bold bg-stone-50 border border-stone-200 px-4 py-3 rounded-2xl text-center">
                          방장({onlineUsers[0]?.username})이 게임을 시작할 수 있습니다.
                        </div>
                      )}
                    </div>
                  )}

                  {/* State 2: SPEAKING TURN PHASE */}
                  {gameStatus === 'speaking' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-stone-200 pb-3">
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-bold text-rose-500 bg-rose-50 border border-rose-100 px-3 py-1 rounded-full">
                            라운드 {round} / 3
                          </span>
                          <span className="text-xs font-bold text-stone-600 bg-stone-50 border border-stone-200 px-3 py-1 rounded-full">
                            카테고리: {gameCategory}
                          </span>
                        </div>
                        
                        {/* Timer Display */}
                        <div className="flex items-center gap-2 bg-stone-50 border border-stone-200 px-4 py-2 rounded-xl">
                          <Clock className="h-4 w-4 text-rose-500 animate-pulse" />
                          <span className="text-sm font-bold font-mono text-stone-700">{formatTimerText(timerSeconds)}</span>
                        </div>
                      </div>

                      {/* Speaker Order list with active spotlight */}
                      <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-none pr-32">
                        {speakingOrder.map((name, idx) => {
                          const isActive = idx === currentSpeakerIndex;
                          const isDone = idx < currentSpeakerIndex;
                          return (
                            <div 
                              key={name} 
                              className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all flex items-center gap-1.5 flex-shrink-0 ${
                                isActive 
                                  ? 'bg-rose-400 text-white shadow-sm scale-105 border border-rose-300' 
                                  : isDone 
                                  ? 'bg-stone-200 text-stone-400 line-through border border-stone-300/40' 
                                  : 'bg-stone-50 text-stone-500 border border-stone-200'
                              }`}
                            >
                              <span>{idx + 1}. {name}</span>
                              {isActive && <span className="h-1.5 w-1.5 rounded-full bg-white animate-ping"></span>}
                            </div>
                          );
                        })}
                      </div>

                      {/* Active Speaker Prompt */}
                      <div className="bg-stone-50 border border-stone-200 rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                          {speakingOrder[currentSpeakerIndex] === username ? (
                            <p className="text-sm font-bold text-rose-500 animate-pulse">
                              👉 당신의 발언 차례입니다! 대화창에 메시지를 입력하고 전송(Enter)하세요!
                            </p>
                          ) : (
                            <p className="text-sm text-stone-600">
                              🎙️ <span className="font-bold text-stone-800">{speakingOrder[currentSpeakerIndex]}</span>님이 발언 중입니다. 경청해 주세요!
                            </p>
                          )}
                        </div>
                      </div>

                      {/* Private Info Card */}
                      {gameLiar === username ? (
                        <div className="bg-gradient-to-r from-rose-50 to-orange-50 border border-rose-200 rounded-2xl p-4 text-rose-800">
                          <h4 className="text-sm font-extrabold flex items-center gap-2">
                            🕵️ 당신은 [라이어]입니다!
                          </h4>
                          <p className="text-xs text-rose-600 mt-1.5 leading-relaxed">
                            제시어를 모르니, 다른 크루원들이 대화 힌트를 입력할 때 눈치껏 정답을 추리하고 안 들키게 연기하세요.
                          </p>
                        </div>
                      ) : (
                        <div className="bg-gradient-to-r from-teal-50 to-stone-50 border border-teal-200 rounded-2xl p-4 flex justify-between items-center gap-4 text-teal-800">
                          <div>
                            <h4 className="text-sm font-extrabold">
                              🛡️ 당신은 [시민]입니다.
                            </h4>
                            <p className="text-xs text-teal-600 mt-1.5 leading-relaxed">
                              라이어가 눈치채지 못하도록 제시어를 적절하게 숨겨 발언하세요.
                            </p>
                          </div>
                          <div className="bg-white border border-teal-200 rounded-2xl px-4 py-2 flex flex-col items-center flex-shrink-0 shadow-sm">
                            <span className="text-[9px] text-stone-400 font-bold uppercase tracking-wider mb-0.5">비밀 제시어</span>
                            <span className="text-base font-black text-rose-500 font-sans">{gameWord}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* State 3: 지목 투표 PHASE */}
                  {gameStatus === 'voting' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="flex items-center justify-between gap-4 border-b border-stone-200 pb-3 pr-32">
                        <div>
                          <h3 className="text-sm font-bold text-amber-500 flex items-center gap-1.5">
                            🗳️ 지목 투표 ({trialNumber}차 지목)
                          </h3>
                          <p className="text-xs text-stone-500 mt-0.5">
                            가장 라이어 같은 사람을 지목하거나, 정보가 부족하면 '한 바퀴 더'에 투표하세요.
                          </p>
                        </div>
                        
                        <div className="flex items-center gap-2 bg-stone-50 border border-stone-200 px-4 py-2 rounded-xl">
                          <Clock className="h-4 w-4 text-amber-500 animate-pulse" />
                          <span className="text-sm font-bold font-mono text-stone-700">{formatTimerText(timerSeconds)}</span>
                        </div>
                      </div>

                      {/* Vote Selection Panel */}
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                        <button
                          onClick={() => handleSubmitVote('one_more')}
                          disabled={votes[username] !== undefined}
                          className={`p-3 rounded-2xl border text-xs font-bold transition-all flex flex-col items-center justify-center gap-1.5 ${
                            votes[username] === 'one_more'
                              ? 'bg-rose-400 border-rose-300 text-white scale-[0.98]'
                              : 'bg-stone-50 border border-stone-200 text-rose-500 hover:bg-stone-100'
                          }`}
                        >
                          <RotateCcw className="h-4 w-4" />
                          <span>🔄 한 바퀴 더</span>
                        </button>
                        <button
                          onClick={() => handleSubmitVote('skip')}
                          disabled={votes[username] !== undefined}
                          className={`p-3 rounded-2xl border text-xs font-bold transition-all flex flex-col items-center justify-center gap-1.5 ${
                            votes[username] === 'skip'
                              ? 'bg-stone-400 border-stone-300 text-white scale-[0.98]'
                              : 'bg-stone-50 border border-stone-200 text-stone-500 hover:bg-stone-100'
                          }`}
                        >
                          <LogOut className="h-4 w-4 rotate-180" />
                          <span>⏭️ 기권</span>
                        </button>

                        {onlineUsers.map((user) => (
                          <button
                            key={user.username}
                            onClick={() => handleSubmitVote(user.username)}
                            disabled={votes[username] !== undefined}
                            className={`p-3 rounded-2xl border text-xs font-bold transition-all flex flex-col items-center justify-center gap-1.5 ${
                              votes[username] === user.username
                                ? 'bg-rose-400 border-rose-300 text-white scale-[0.98]'
                                : 'bg-white border border-stone-200 text-stone-700 hover:bg-stone-100 shadow-sm'
                            }`}
                          >
                            <div className={`h-6 w-6 rounded-md bg-gradient-to-br ${getAvatarGradient(user.username)} flex items-center justify-center text-[10px] font-bold text-white shadow-sm flex-shrink-0`}>
                              {getInitials(user.username)}
                            </div>
                            <span>{user.username} {user.username === username && '(나)'}</span>
                          </button>
                        ))}
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-4 text-xs font-semibold text-stone-500">
                        <span>투표 현황: {Object.keys(votes).length} / {onlineUsers.length}명 참여</span>
                        {votes[username] && <span className="text-emerald-600">투표가 제출되었습니다.</span>}
                      </div>
                    </div>
                  )}

                  {/* State 4: 최후 변론 및 찬반 투표 PHASE */}
                  {gameStatus === 'defense' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="flex items-center justify-between gap-4 border-b border-stone-200 pb-3 pr-32">
                        <div>
                          <h3 className="text-sm font-bold text-rose-500">
                            ⚖️ 최후 변론 및 처형 찬반 투표
                          </h3>
                          <p className="text-xs text-stone-500 mt-0.5">
                            지목된 크루원의 최후 변론을 듣고 처형([죽이기]) 또는 방면([살리기])에 투표하세요.
                          </p>
                        </div>

                        <div className="flex items-center gap-2 bg-stone-50 border border-stone-200 px-4 py-2 rounded-xl">
                          <Clock className="h-4 w-4 text-rose-500 animate-pulse" />
                          <span className="text-sm font-bold font-mono text-stone-700">{formatTimerText(timerSeconds)}</span>
                        </div>
                      </div>

                      {/* Spotlight on nominated player */}
                      <div className="bg-rose-50 border border-rose-100 rounded-3xl p-5 text-center flex flex-col items-center justify-center gap-3">
                        <div className={`h-12 w-12 rounded-2xl bg-gradient-to-br ${getAvatarGradient(nominatedPlayer)} flex items-center justify-center text-base font-bold text-white shadow-md animate-bounce`}>
                          {getInitials(nominatedPlayer)}
                        </div>
                        <div>
                          <span className="text-xs text-stone-400 font-bold block">변론자</span>
                          <h4 className="text-base font-extrabold text-stone-700 mt-0.5">{nominatedPlayer} {nominatedPlayer === username && '(나)'}</h4>
                        </div>
                        {nominatedPlayer === username ? (
                          <p className="text-xs text-rose-500 font-bold max-w-md">
                            당신은 지목되었습니다! 40초간 변론하여 혐의를 탈피하고 생존을 도모하십시오.
                          </p>
                        ) : (
                          <p className="text-xs text-stone-500 max-w-md">
                            {nominatedPlayer}님의 변론을 다 듣고 아래 처형 투표에 동참해 주세요.
                          </p>
                        )}
                      </div>

                      {/* Verdict vote buttons (Blocked for the defender) */}
                      {nominatedPlayer !== username ? (
                        <div className="grid grid-cols-2 gap-4">
                          <button
                            onClick={() => handleSubmitDefenseVote('kill')}
                            disabled={defenseVotes[username] !== undefined}
                            className={`py-3.5 rounded-full border text-sm font-bold transition-all flex items-center justify-center gap-2 shadow-sm ${
                              defenseVotes[username] === 'kill'
                                ? 'bg-rose-500 border-rose-400 text-white scale-[0.98]'
                                : 'bg-stone-100 border border-stone-200 text-rose-500 hover:bg-stone-100'
                            }`}
                          >
                            <span>처형 (죽이기 🔪)</span>
                          </button>
                          <button
                            onClick={() => handleSubmitDefenseVote('spare')}
                            disabled={defenseVotes[username] !== undefined}
                            className={`py-3.5 rounded-full border text-sm font-bold transition-all flex items-center justify-center gap-2 shadow-sm ${
                              defenseVotes[username] === 'spare'
                                ? 'bg-teal-500 border-teal-400 text-white scale-[0.98]'
                                : 'bg-stone-100 border border-stone-200 text-teal-500 hover:bg-stone-100'
                            }`}
                          >
                            <span>방면 (살리기 🕊️)</span>
                          </button>
                        </div>
                      ) : (
                        <div className="bg-stone-50 border border-stone-200 p-4 rounded-2xl text-center text-xs text-stone-500 font-bold">
                          변론 당사자는 투표에 참여할 수 없습니다.
                        </div>
                      )}

                      <div className="flex justify-between items-center text-xs text-stone-500 font-semibold">
                        <span>투표 현황: {Object.keys(defenseVotes).length} / {onlineUsers.length - 1}명 참여</span>
                        {defenseVotes[username] && <span className="text-emerald-600">변론 투표 완료.</span>}
                      </div>
                    </div>
                  )}

                  {/* State 5: 라이어 제시어 역전 찬스 (Liar guessing) */}
                  {gameStatus === 'liar_guess' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="flex items-center justify-between gap-4 border-b border-stone-200 pb-3 pr-32">
                        <div>
                          <h3 className="text-sm font-bold text-rose-500 flex items-center gap-2">
                            <RotateCcw className="h-4.5 w-4.5 animate-spin-slow" />
                            <span>🔄 라이어 역전 정답 찬스! (2분)</span>
                          </h3>
                          <p className="text-xs text-stone-500 mt-0.5">
                            라이어 정체는 밝혀졌으나, 제시어를 유추해 맞출 경우 라이어가 역전 우승합니다.
                          </p>
                        </div>

                        <div className="flex items-center gap-2 bg-stone-50 border border-stone-200 px-4 py-2 rounded-xl">
                          <Clock className="h-4 w-4 text-rose-500 animate-pulse" />
                          <span className="text-sm font-bold font-mono text-stone-700">{formatTimerText(timerSeconds)}</span>
                        </div>
                      </div>

                      {/* Guessing input (Only available for the Liar) */}
                      {gameLiar === username ? (
                        <form onSubmit={handleLiarGuessSubmit} className="space-y-3">
                          <label htmlFor="guess-input" className="block text-xs font-bold text-stone-500">
                            정확한 제시어 입력 (카테고리: {gameCategory})
                          </label>
                          <div className="flex gap-3">
                            <input
                              id="guess-input"
                              type="text"
                              required
                              placeholder="제시어 정답을 입력하세요 (공백 무시 판정)"
                              value={liarGuessText}
                              onChange={(e) => setLiarGuessText(e.target.value)}
                              className="flex-1 px-4 py-3 bg-stone-50 border border-stone-200 rounded-2xl text-stone-800 placeholder-stone-500 focus:outline-none focus:border-rose-400 focus:ring-1 focus:ring-rose-500 font-medium"
                            />
                            <button
                              type="submit"
                              className="py-3 px-6 rounded-full bg-rose-400 hover:bg-rose-500 text-white font-bold text-sm shadow-md hover:-translate-y-0.5 transition-all active:scale-95 flex-shrink-0"
                            >
                              정답 제출
                            </button>
                          </div>
                        </form>
                      ) : (
                        <div className="bg-stone-50 border border-stone-200 p-6 rounded-2xl text-center">
                          <p className="text-sm font-bold text-rose-500 animate-pulse">
                            🕵️ 라이어 [{gameLiar}]님이 제시어를 유추하여 입력하고 있습니다...
                          </p>
                          <span className="text-[10px] text-stone-500 font-bold block mt-1.5">
                            정답 유추에 성공할 경우 라이어가 역전 승점을 획득합니다.
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* State 6: ROUND RESULT */}
                  {gameStatus === 'result' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                        <div className="flex-1 space-y-3 w-full">
                          <div className="flex items-center gap-2 text-rose-500">
                            <Sparkles className="h-5 w-5 animate-pulse" />
                            <h2 className="text-base font-black tracking-tight">🏆 라운드 {round} 종료! 결과가 판가름 났습니다.</h2>
                          </div>
                          
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="bg-stone-50 border border-stone-200 rounded-2xl p-4 flex items-center gap-3">
                              <div className={`h-8 w-8 rounded-lg bg-gradient-to-br ${getAvatarGradient(gameLiar)} flex items-center justify-center text-xs font-bold text-white shadow-sm flex-shrink-0`}>
                                {getInitials(gameLiar)}
                              </div>
                              <div>
                                <span className="text-[10px] text-stone-500 font-bold block">라이어</span>
                                <span className="text-sm font-bold text-red-500">{gameLiar}</span>
                              </div>
                            </div>

                            <div className="bg-stone-50 border border-stone-200 rounded-2xl p-4 flex flex-col justify-center">
                              <span className="text-[10px] text-stone-500 font-bold block mb-0.5">정답 제시어</span>
                              <span className="text-sm font-black text-rose-500 tracking-wide">{gameWord} (카테고리: {gameCategory})</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* State 7: FINAL SCOREBOARD */}
                  {gameStatus === 'final_scoreboard' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                      <div className="text-center pb-2">
                        <h2 className="text-lg font-black text-rose-500 flex items-center justify-center gap-2">
                          👑 라이어 게임 최종 랭킹 스코어보드 👑
                        </h2>
                        <p className="text-xs text-stone-500 mt-1">3라운드 동안의 누적 점수를 바탕으로 계산된 최종 순위입니다.</p>
                      </div>

                      {/* Sorted score listing */}
                      <div className="space-y-2 max-h-52 overflow-y-auto">
                        {Object.entries(scores)
                          .sort((a, b) => b[1] - a[1])
                          .map(([name, score], idx) => {
                            const isWinner = idx === 0;
                            return (
                              <div 
                                key={name}
                                className={`flex items-center justify-between p-3.5 rounded-2xl border transition-all ${
                                  isWinner 
                                    ? 'bg-rose-100/50 border-rose-200/70 text-rose-800 shadow-sm' 
                                    : 'bg-stone-50 border-stone-200 text-stone-600'
                                }`}
                              >
                                <div className="flex items-center gap-3">
                                  <span className={`text-sm font-black w-6 text-center ${isWinner ? 'text-rose-500' : 'text-stone-400'}`}>
                                    {idx + 1}
                                  </span>
                                  <div className={`h-7 w-7 rounded-lg bg-gradient-to-br ${getAvatarGradient(name)} flex items-center justify-center text-xs font-bold text-white shadow-sm`}>
                                    {getInitials(name)}
                                  </div>
                                  <span className={`text-sm font-bold ${isWinner ? 'text-rose-700 font-extrabold' : ''}`}>{name}</span>
                                </div>
                                <span className={`text-sm font-black font-mono ${isWinner ? 'text-rose-500' : 'text-stone-500'}`}>
                                  {score}점
                                </span>
                              </div>
                            );
                          })}
                      </div>

                      {/* Reset Controls */}
                      {isHost && (
                        <div className="flex justify-end pt-2">
                          <button
                            onClick={handleResetGame}
                            className="w-full md:w-auto py-3 px-6 rounded-full bg-stone-200 hover:bg-stone-300 text-stone-700 text-xs font-bold hover:-translate-y-0.5 active:scale-95 transition-all shadow-sm flex items-center justify-center gap-2"
                          >
                            <RotateCcw className="h-4 w-4" />
                            대기실로 돌아가기 (점수 초기화)
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                </div>
              </div>
            </div>
          )}

          {/* Scrollable messages container */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6 flex flex-col bg-stone-50/10">
            <div className="max-w-4xl mx-auto w-full flex-grow">
              {/* Chat message listing */}
              {loading ? (
                <div className="flex flex-col items-center justify-center flex-grow gap-2 text-stone-500 my-auto">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-stone-200 border-t-rose-500"></div>
                  <span className="text-xs font-medium">채팅 내역을 불러오는 중...</span>
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center flex-grow gap-3 p-8 text-center text-stone-500 max-w-sm mx-auto my-auto animate-in fade-in duration-300">
                  <div className="h-12 w-12 rounded-2xl bg-white border border-stone-200 flex items-center justify-center shadow-sm">
                    <Sparkles className="h-6 w-6 text-rose-400" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-stone-700">방 번호 {roomId}에 첫 입장!</h3>
                    <p className="text-xs text-stone-500 mt-1 leading-relaxed">
                      {roomType === 'liar' 
                        ? '라이어 게임방에 아직 주고받은 대화가 없습니다. 상단의 방 번호를 복사해 친구를 초대하고 첫 실시간 게임 메시지를 보내보세요!'
                        : '대기실 채팅방에 아직 주고받은 메시지가 없습니다. 상단의 방 번호를 복사해 친구를 초대하고 첫 실시간 대화를 나눠보세요!'
                      }
                    </p>
                  </div>
                </div>
              ) : (
                <div className="max-w-4xl mx-auto w-full space-y-4 flex-grow">
                  {messages.map((msg, index) => {
                    const isMe = msg.username === username;
                    const isSystem = msg.username === '📢 시스템';
                    
                    if (isSystem) {
                      return (
                        <div key={msg.id || index} className="flex justify-center my-3 animate-in fade-in duration-300">
                          <div className="bg-stone-100 border border-stone-200 rounded-2xl px-6 py-4 max-w-xl text-center shadow-sm">
                            <p className="text-sm font-bold text-stone-700 whitespace-pre-wrap leading-relaxed">
                              {msg.text}
                            </p>
                            <span className="text-[9px] text-stone-400 font-bold block mt-2 tracking-wide font-mono uppercase">
                              SYSTEM ANNOUNCEMENT • {formatTime(msg.created_at)}
                            </span>
                          </div>
                        </div>
                      );
                    }

                    const showHeader = index === 0 || messages[index - 1].username !== msg.username;
                    
                    return (
                      <div 
                        key={msg.id || index} 
                        className={`flex flex-col ${isMe ? 'items-end' : 'items-start'} ${showHeader ? 'mt-4' : 'mt-1'}`}
                      >
                        {/* User Header */}
                        {!isMe && showHeader && (
                          <div className="flex items-center gap-2 mb-1 pl-1">
                            <div className={`h-5 w-5 rounded-md bg-gradient-to-br ${getAvatarGradient(msg.username)} flex items-center justify-center text-[10px] font-bold text-white shadow-sm`}>
                              {getInitials(msg.username)}
                            </div>
                            <span className="text-xs font-bold text-stone-600">{msg.username}</span>
                          </div>
                        )}

                        {/* Message Bubble + Time Row */}
                        <div className={`flex items-end gap-2 max-w-[85%] ${isMe ? 'flex-row-reverse' : 'flex-row'}`}>
                          {/* Bubble */}
                          <div 
                            className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words shadow-sm transition-all ${
                              isMe 
                                ? 'bg-rose-200 text-stone-800 rounded-tr-none border border-rose-300/40' 
                                : 'bg-white text-stone-800 rounded-tl-none border border-stone-200/80'
                            }`}
                          >
                            {msg.text}
                          </div>

                          {/* Timestamp */}
                          <span className="text-[10px] text-stone-400 font-medium flex items-center gap-0.5 flex-shrink-0 pb-1">
                            <Clock className="h-2.5 w-2.5 text-stone-400" />
                            {formatTime(msg.created_at)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            
            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Chat Input Form */}
          <div className="flex-shrink-0 p-4 bg-stone-100/90 border-t border-stone-200/80 backdrop-blur-md">
            <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto flex items-center gap-3">
              <div className="flex-1 relative">
                <input
                  type="text"
                  required
                  disabled={loading}
                  placeholder={
                    gameStatus === 'speaking' && speakingOrder[currentSpeakerIndex] === username
                      ? "당신의 발언 차례입니다! 여기에 힌트를 입력하고 전송하세요..."
                      : roomType === 'liar' 
                      ? "메시지를 입력하세요..." 
                      : "대기실 크루원들과 대화할 메시지를 입력하세요..."
                  }
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  className="block w-full px-5 py-4 bg-white border border-stone-200 rounded-2xl text-stone-800 placeholder-stone-400 focus:outline-none focus:border-rose-400 focus:ring-2 focus:ring-rose-400/10 transition-all font-medium text-sm md:text-base disabled:opacity-50"
                />
              </div>

              <button
                type="submit"
                disabled={!inputText.trim() || sending || loading}
                className="p-4 rounded-2xl bg-gradient-to-r from-rose-400 to-amber-300 hover:from-rose-500 hover:to-amber-400 text-white shadow-md hover:-translate-y-0.5 active:scale-[0.96] disabled:opacity-50 disabled:pointer-events-none transition-all flex-shrink-0"
                title="메시지 전송"
              >
                <Send className="h-5 w-5" />
              </button>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
