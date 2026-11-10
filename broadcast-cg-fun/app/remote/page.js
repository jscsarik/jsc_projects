'use client';

import { useState, useEffect, useRef } from 'react';
import { supabase } from '../../lib/supabaseClient';

// 인기 GIF & 짤방 프리셋 (영웅, 명장 제외)
const PRESET_GIFS = [
  {
    name: '👏 박수 뚱이',
    url: 'https://media1.tenor.com/m/4Mcm-SxPJX4AAAAC/spongebob.gif',
  },
  {
    name: '😸 냥이',
    url: 'https://media1.tenor.com/m/r4M8OQcK-HsAAAAC/laughing-cat.gif',
  },
];

// 다양한 TTS 목소리 목록
const VOICES = [
  { id: 'woman', label: '👧 여성 (기본)' },
  { id: 'man', label: '🧔 굵은 남성' },
  { id: 'baby', label: '👶 애기/잼민이' },
  { id: 'fast', label: '⚡ 속사포' },
];

export default function RemotePage() {
  const [text, setText] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [selectedVoice, setSelectedVoice] = useState('woman'); // woman, man, baby, fast
  const [videoDuration, setVideoDuration] = useState(10); // 10초, 20초, 30초 (유튜브 전용)
  const [isSending, setIsSending] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [toastType, setToastType] = useState('success');

  const channelRef = useRef(null);

  useEffect(() => {
    const channel = supabase.channel('overlay-channel');
    channel.subscribe();
    channelRef.current = channel;

    return () => {
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current);
      }
    };
  }, []);

  const showToast = (message, type = 'success') => {
    setToastMessage(message);
    setToastType(type);
    setTimeout(() => {
      setToastMessage('');
    }, 3000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const trimmedText = text.trim();
    const trimmedImageUrl = imageUrl.trim();
    const trimmedYoutubeUrl = youtubeUrl.trim();

    if (!trimmedText && !trimmedImageUrl && !trimmedYoutubeUrl) {
      showToast('메시지, 이미지(GIF), 유튜브 중 하나 이상을 입력해주세요!', 'error');
      return;
    }

    setIsSending(true);

    try {
      const channel = channelRef.current || supabase.channel('overlay-channel');

      await channel.send({
        type: 'broadcast',
        event: 'new_message',
        payload: {
          text: trimmedText,
          imageUrl: trimmedImageUrl,
          youtubeUrl: trimmedYoutubeUrl,
          voice: selectedVoice, // 선택한 목소리 (woman, man, baby, fast)
          duration: trimmedYoutubeUrl ? videoDuration * 1000 : null,
          sentAt: new Date().toISOString(),
        },
      });

      setText('');
      setImageUrl('');
      setYoutubeUrl('');
      showToast('🎉 방송 화면으로 전송 완료!');
    } catch (error) {
      console.error('[전송 에러]', error);
      showToast('전송 중 오류가 발생했습니다. 다시 시도해주세요.', 'error');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main
      style={{
        minHeight: '100vh',
        backgroundColor: '#0a0b0e',
        color: '#f1f5f9',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '20px 16px',
        boxSizing: 'border-box',
        fontFamily: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      {/* 토스트 알림 */}
      {toastMessage && (
        <div
          style={{
            position: 'fixed',
            top: '20px',
            zIndex: 9999,
            padding: '12px 24px',
            borderRadius: '16px',
            fontWeight: 800,
            fontSize: '15px',
            color: '#ffffff',
            backgroundColor: toastType === 'success' ? '#059669' : '#e11d48',
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
          }}
        >
          {toastMessage}
        </div>
      )}

      {/* 리모컨 카드 */}
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          backgroundColor: '#12151c',
          border: '1.5px solid rgba(255, 255, 255, 0.12)',
          borderRadius: '28px',
          padding: '28px 20px',
          boxShadow: '0 25px 50px rgba(0, 0, 0, 0.7)',
          boxSizing: 'border-box',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
          <div style={{ fontSize: '36px', marginBottom: '6px' }}>📡</div>
          <h1
            style={{
              margin: '0 0 4px 0',
              fontSize: '24px',
              fontWeight: 800,
              color: '#ffffff',
            }}
          >
            실시간 전광판 리모컨
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>
            다양한 목소리(여성/남성/애기), GIF 짤방, 유튜브 영도 송출!
          </p>
        </div>

        {/* 1. 인기 GIF 짤방 프리셋 */}
        <div style={{ marginBottom: '16px' }}>
          <div
            style={{
              fontSize: '12px',
              fontWeight: 800,
              color: '#c084fc',
              marginBottom: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🔥</span> 인기 GIF 짤 바로 넣기 (원클릭)
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {PRESET_GIFS.map((gif, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setImageUrl(gif.url);
                  showToast(`${gif.name} 짤 선택됨!`);
                }}
                style={{
                  backgroundColor: '#1e2433',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '12px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#e2e8f0',
                  cursor: 'pointer',
                }}
              >
                {gif.name}
              </button>
            ))}
          </div>
        </div>

        {/* 2. 유명 짤방/GIF 사이트 링크 */}
        <div
          style={{
            backgroundColor: 'rgba(255, 255, 255, 0.04)',
            border: '1px dashed rgba(255, 255, 255, 0.15)',
            borderRadius: '16px',
            padding: '10px 14px',
            marginBottom: '16px',
            fontSize: '12px',
            color: '#94a3b8',
          }}
        >
          <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: '6px' }}>
            🌐 추천 짤 사이트 (우클릭 [이미지 주소 복사]):
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <a
              href="https://tenor.com"
              target="_blank"
              rel="noreferrer"
              style={{
                color: '#38bdf8',
                textDecoration: 'none',
                backgroundColor: 'rgba(56, 189, 248, 0.1)',
                padding: '3px 8px',
                borderRadius: '8px',
                fontWeight: 700,
              }}
            >
              Tenor GIF ↗
            </a>
            <a
              href="https://giphy.com"
              target="_blank"
              rel="noreferrer"
              style={{
                color: '#a855f7',
                textDecoration: 'none',
                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                padding: '3px 8px',
                borderRadius: '8px',
                fontWeight: 700,
              }}
            >
              GIPHY ↗
            </a>
          </div>
        </div>

        {/* 메인 입력 폼 */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '13px',
                fontWeight: 700,
                color: '#cbd5e1',
                marginBottom: '6px',
              }}
            >
              💬 방송에 띄울 메시지 (4초 노출)
            </label>
            <textarea
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="화면에 띄우고 읽어줄 메시지를 적어주세요!"
              style={{
                width: '100%',
                backgroundColor: '#1a1f2b',
                border: '1px solid #2d3748',
                borderRadius: '16px',
                padding: '12px 14px',
                fontSize: '15px',
                color: '#ffffff',
                boxSizing: 'border-box',
                resize: 'none',
                outline: 'none',
              }}
            />

            {/* 🗣️ 목소리 선택 섹션 */}
            <div style={{ marginTop: '10px' }}>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#94a3b8',
                  marginBottom: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span>🗣️</span> TTS 목소리 선택:
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {VOICES.map((v) => (
                  <button
                    key={v.id}
                    type="button"
                    onClick={() => setSelectedVoice(v.id)}
                    style={{
                      flex: '1 1 45%',
                      padding: '8px 4px',
                      borderRadius: '12px',
                      fontSize: '12px',
                      fontWeight: 800,
                      cursor: 'pointer',
                      border: selectedVoice === v.id ? '2px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.1)',
                      backgroundColor: selectedVoice === v.id ? 'rgba(99, 102, 241, 0.25)' : '#1a1f2b',
                      color: selectedVoice === v.id ? '#a5b4fc' : '#cbd5e1',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {v.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <label
                style={{
                  fontSize: '13px',
                  fontWeight: 700,
                  color: '#cbd5e1',
                }}
              >
                🖼️ 이미지 또는 GIF 움짤 URL (4초 노출)
              </label>
              {imageUrl && (
                <button
                  type="button"
                  onClick={() => setImageUrl('')}
                  style={{
                    fontSize: '11px',
                    color: '#f87171',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  지우기
                </button>
              )}
            </div>
            <input
              type="url"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              placeholder="https://.../sample.gif (자동으로 4초간 표시됩니다)"
              style={{
                width: '100%',
                backgroundColor: '#1a1f2b',
                border: '1px solid #2d3748',
                borderRadius: '16px',
                padding: '12px 14px',
                fontSize: '14px',
                color: '#ffffff',
                boxSizing: 'border-box',
                outline: 'none',
              }}
            />
          </div>

          {/* 유튜브 입력 섹션 */}
          <div
            style={{
              backgroundColor: 'rgba(239, 68, 68, 0.06)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: '18px',
              padding: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <label
                style={{
                  fontSize: '13px',
                  fontWeight: 800,
                  color: '#fca5a5',
                }}
              >
                🎬 유튜브 영도 링크 (시간 선택 가능)
              </label>
              <button
                type="button"
                onClick={() => {
                  setYoutubeUrl('https://www.youtube.com/watch?v=aqz-KE-bpKQ');
                  showToast('신나는 빅벅버니 샘플 영상 입력됨!');
                }}
                style={{
                  fontSize: '11px',
                  color: '#f87171',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 700,
                }}
              >
                샘플 링크 넣기
              </button>
            </div>
            <input
              type="url"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              style={{
                width: '100%',
                backgroundColor: '#1a1f2b',
                border: '1px solid #2d3748',
                borderRadius: '14px',
                padding: '12px 14px',
                fontSize: '14px',
                color: '#ffffff',
                boxSizing: 'border-box',
                outline: 'none',
              }}
            />

            {/* 유튜브 재생 시간 선택 (10초 / 20초 / 30초) */}
            <div style={{ marginTop: '10px' }}>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 700,
                  color: '#f87171',
                  marginBottom: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span>⏱️</span> 유튜브 재생 시간 선택:
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                {[10, 20, 30].map((sec) => (
                  <button
                    key={sec}
                    type="button"
                    onClick={() => setVideoDuration(sec)}
                    style={{
                      flex: 1,
                      padding: '8px 0',
                      borderRadius: '12px',
                      fontSize: '13px',
                      fontWeight: 800,
                      cursor: 'pointer',
                      border: videoDuration === sec ? '2px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.1)',
                      backgroundColor: videoDuration === sec ? '#ef4444' : '#1a1f2b',
                      color: '#ffffff',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {sec}초
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSending}
            style={{
              marginTop: '6px',
              width: '100%',
              padding: '16px',
              borderRadius: '18px',
              fontSize: '17px',
              fontWeight: 800,
              color: '#ffffff',
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%)',
              border: 'none',
              cursor: isSending ? 'not-allowed' : 'pointer',
              opacity: isSending ? 0.6 : 1,
              boxShadow: '0 10px 25px rgba(99, 102, 241, 0.4)',
              transition: 'transform 0.1s ease',
            }}
          >
            {isSending ? '전송 중...' : '🚀 방송 화면으로 쏘기'}
          </button>
        </form>
      </div>
    </main>
  );
}
