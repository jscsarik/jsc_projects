'use client';

import { useState, useEffect, useRef } from 'react';
import { supabase } from '../../lib/supabaseClient';

function extractYouTubeId(url) {
  if (!url) return null;
  const str = url.trim();
  const regExp = /(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|v\/|shorts\/|live\/)|youtu\.be\/)([\w-]{11})/;
  const match = str.match(regExp);
  if (match && match[1]) return match[1];
  if (/^[\w-]{11}$/.test(str)) return str;
  return null;
}

export default function OverlayScreenPage() {
  const [overlayData, setOverlayData] = useState(null);
  const [isVisible, setIsVisible] = useState(false);
  const hideTimerRef = useRef(null);
  const currentAudioRef = useRef(null);

  // OBS 호환 맑은 3단 차임벨 효과음
  const playNotificationSound = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      if (ctx.state === 'suspended') {
        ctx.resume();
      }

      const playTone = (freq, delay, duration) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, ctx.currentTime + delay);

        gain.gain.setValueAtTime(0, ctx.currentTime + delay);
        gain.gain.linearRampToValueAtTime(0.35, ctx.currentTime + delay + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + duration);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(ctx.currentTime + delay);
        osc.stop(ctx.currentTime + delay + duration);
      };

      playTone(523.25, 0.0, 0.3); // C5
      playTone(659.25, 0.12, 0.3); // E5
      playTone(783.99, 0.24, 0.5); // G5
    } catch (e) {
      console.warn('[오디오 재생 실패]', e);
    }
  };

  // 목소리별 피치(음높이) 대폭 강화 튜닝
  const playKoreanTts = (text, voiceType = 'woman', onEndCallback) => {
    try {
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }

      let finished = false;
      const finish = () => {
        if (!finished) {
          finished = true;
          if (onEndCallback) onEndCallback();
        }
      };

      const ttsUrl = `/api/tts?text=${encodeURIComponent(text)}&t=${Date.now()}`;
      const audio = new Audio(ttsUrl);
      audio.volume = 1.0;

      // 브라우저 내장 오디오 피치 변조 속성 적용
      audio.preservesPitch = false;
      audio.mozPreservesPitch = false;
      audio.webkitPreservesPitch = false;

      if (voiceType === 'man') {
        // 🧔 묵직한 동굴 저음 남성 (피치 대폭 다운)
        audio.playbackRate = 0.72;
      } else if (voiceType === 'baby') {
        // 👶 헬륨가스 애기/잼민이 (초고음 피치)
        audio.playbackRate = 1.62;
      } else if (voiceType === 'fast') {
        // ⚡ 속사포 래퍼
        audio.preservesPitch = true;
        audio.playbackRate = 1.55;
      } else {
        // 👧 상큼하고 확실한 진짜 여성 톤 (사용자 요청: 피치를 1.33배로 대폭 상향!)
        audio.playbackRate = 1.33;
      }

      currentAudioRef.current = audio;

      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);

      setTimeout(() => {
        if (!finished) finish();
      }, 9000);
    } catch (err) {
      console.error('[TTS 에러]', err);
      if (onEndCallback) onEndCallback();
    }
  };

  const scheduleHide = (delayMs) => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => {
      setIsVisible(false);
      setTimeout(() => {
        setOverlayData(null);
      }, 500);
    }, delayMs);
  };

  useEffect(() => {
    const channel = supabase.channel('overlay-channel');

    channel
      .on('broadcast', { event: 'new_message' }, ({ payload }) => {
        console.log('[수신 성공]', payload);

        if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
        if (currentAudioRef.current) {
          currentAudioRef.current.pause();
          currentAudioRef.current = null;
        }

        const text = payload.text || payload.message || '';
        const imageUrl = payload.imageUrl || payload.image || null;
        const rawYoutubeUrl = payload.youtubeUrl || payload.videoUrl || null;
        const youtubeId = extractYouTubeId(rawYoutubeUrl);
        const customDuration = payload.duration;
        const voiceType = payload.voice || 'woman';

        let activeDuration = 4000;
        let durationLabel = '';

        if (youtubeId) {
          activeDuration = customDuration || 10000;
          durationLabel = `${Math.round(activeDuration / 1000)}초`;
        }

        const voiceLabels = {
          woman: '👧 여성',
          man: '🧔 남성',
          baby: '👶 애기/잼민이',
          fast: '⚡ 속사포',
        };

        setOverlayData({
          text,
          imageUrl,
          youtubeId,
          durationLabel,
          voiceLabel: voiceLabels[voiceType] || '👧 여성',
        });
        setIsVisible(true);

        playNotificationSound();

        if (youtubeId) {
          scheduleHide(activeDuration);
        } else if (text) {
          setTimeout(() => {
            playKoreanTts(text, voiceType, () => {
              scheduleHide(3500);
            });
          }, 350);
        } else {
          scheduleHide(4000);
        }
      })
      .subscribe();

    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
      if (currentAudioRef.current) {
        currentAudioRef.current.pause();
        currentAudioRef.current = null;
      }
      supabase.removeChannel(channel);
    };
  }, []);

  const hasMedia = Boolean(overlayData?.imageUrl || overlayData?.youtubeId);

  return (
    <main
      style={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        backgroundColor: 'transparent',
        pointerEvents: 'none',
        userSelect: 'none',
        boxSizing: 'border-box',
        overflow: 'hidden',
        fontFamily: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      {/* [CASE 1] 유튜브 또는 이미지/GIF */}
      {hasMedia && (
        <div
          style={{
            position: 'absolute',
            top: '40px',
            right: '40px',
            maxWidth: '500px',
            width: '90%',
            opacity: isVisible && overlayData ? 1 : 0,
            transform: isVisible && overlayData ? 'translateX(0) scale(1)' : 'translateX(60px) scale(0.92)',
            transition: 'all 0.45s cubic-bezier(0.16, 1, 0.3, 1)',
            backgroundColor: 'rgba(13, 15, 20, 0.96)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: overlayData.youtubeId ? '2px solid rgba(239, 68, 68, 0.8)' : '2px solid rgba(168, 85, 247, 0.8)',
            borderRadius: '24px',
            padding: '18px',
            boxShadow: overlayData.youtubeId
              ? '0 25px 60px rgba(0, 0, 0, 0.9), 0 0 40px rgba(239, 68, 68, 0.35)'
              : '0 25px 60px rgba(0, 0, 0, 0.9), 0 0 40px rgba(168, 85, 247, 0.35)',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
            boxSizing: 'border-box',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 4px',
            }}
          >
            <div
              style={{
                fontSize: '13px',
                fontWeight: 800,
                letterSpacing: '0.12em',
                color: overlayData.youtubeId ? '#f87171' : '#c084fc',
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: overlayData.youtubeId ? '#ef4444' : '#a855f7',
                  boxShadow: overlayData.youtubeId ? '0 0 10px #ef4444' : '0 0 10px #a855f7',
                }}
              />
              {overlayData.youtubeId
                ? `YOUTUBE DONATION (${overlayData.durationLabel})`
                : 'IMAGE / GIF DONATION (4초)'}
            </div>
            <span
              style={{
                fontSize: '11px',
                color: overlayData.youtubeId ? '#ef4444' : '#34d399',
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                padding: '2px 8px',
                borderRadius: '8px',
                fontWeight: 700,
              }}
            >
              LIVE
            </span>
          </div>

          {overlayData.youtubeId && (
            <div
              style={{
                width: '100%',
                borderRadius: '16px',
                overflow: 'hidden',
                backgroundColor: '#000000',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                aspectRatio: '16 / 9',
                position: 'relative',
              }}
            >
              <iframe
                key={overlayData.youtubeId}
                src={`https://www.youtube.com/embed/${overlayData.youtubeId}?autoplay=1&mute=0&controls=1&playsinline=1`}
                title="YouTube video player"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  border: 'none',
                }}
              />
            </div>
          )}

          {overlayData.imageUrl && !overlayData.youtubeId && (
            <div
              style={{
                width: '100%',
                borderRadius: '16px',
                overflow: 'hidden',
                backgroundColor: '#000000',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                maxHeight: '480px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <img
                src={overlayData.imageUrl}
                alt="방송 짤/GIF"
                style={{
                  width: '100%',
                  maxHeight: '480px',
                  objectFit: 'contain',
                  display: 'block',
                }}
              />
            </div>
          )}

          {overlayData?.text && (
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.06)',
                borderRadius: '14px',
                padding: '12px 16px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontSize: '22px',
                  fontWeight: 800,
                  color: '#ffffff',
                  lineHeight: 1.35,
                  wordBreak: 'break-word',
                  textShadow: '0 2px 8px rgba(0, 0, 0, 0.9)',
                }}
              >
                {overlayData.text}
              </p>
            </div>
          )}
        </div>
      )}

      {/* [CASE 2] 텍스트만 있을 때: 화면 하단 전광판 */}
      {!hasMedia && (
        <div
          style={{
            position: 'absolute',
            bottom: '40px',
            left: '50%',
            maxWidth: '900px',
            width: '90%',
            opacity: isVisible && overlayData ? 1 : 0,
            transform: isVisible && overlayData
              ? 'translateX(-50%) translateY(0) scale(1)'
              : 'translateX(-50%) translateY(40px) scale(0.96)',
            transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
            backgroundColor: 'rgba(15, 17, 23, 0.92)',
            backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            border: '1.5px solid rgba(255, 255, 255, 0.2)',
            borderRadius: '24px',
            padding: '24px 30px',
            boxShadow: '0 20px 50px rgba(0, 0, 0, 0.8), 0 0 30px rgba(99, 102, 241, 0.2)',
            display: 'flex',
            alignItems: 'center',
            gap: '24px',
            color: '#ffffff',
            boxSizing: 'border-box',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: '13px',
                fontWeight: 800,
                letterSpacing: '0.15em',
                color: '#34d399',
                textTransform: 'uppercase',
                marginBottom: '6px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: '#34d399',
                  boxShadow: '0 0 10px #34d399',
                }}
              />
              LIVE MESSAGE ({overlayData?.voiceLabel || '👧 여성'})
            </div>

            <p
              style={{
                margin: 0,
                fontSize: '28px',
                fontWeight: 800,
                color: '#ffffff',
                lineHeight: 1.35,
                wordBreak: 'break-word',
                textShadow: '0 2px 8px rgba(0, 0, 0, 0.9)',
              }}
            >
              {overlayData?.text}
            </p>
          </div>
        </div>
      )}
    </main>
  );
}
