import React, { useState, useEffect, useRef } from 'react';
import { supabase } from '../lib/supabaseClient';
import type { Session } from '@supabase/supabase-js';
import { audioManager } from '../lib/audioManager';

interface DBMessage {
  id: string | number;
  sender: string;
  text: string;
  created_at: string;
}

interface ChatProps {
  session: Session;
}

export const Chat: React.FC<ChatProps> = ({ session }) => {
  const userEmail = session.user?.email || 'unknown@official-chat.com';
  
  // Helper to extract clean company ID from the internal email format
  const getCompanyId = (emailStr: string): string => {
    if (!emailStr) return 'Anonymous';
    return emailStr.replace('@official-chat.com', '');
  };

  const currentCompanyId = getCompanyId(userEmail);

  // Message and layout states
  const [messages, setMessages] = useState<DBMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Call-related state variables
  const [onlineUsers, setOnlineUsers] = useState<string[]>([]);
  const [showSidebar, setShowSidebar] = useState(true);
  const [joinNotice, setJoinNotice] = useState<string | null>(null);
  const [showUserListModal, setShowUserListModal] = useState(false);
  const [callState, setCallState] = useState<{
    type: 'idle' | 'dialing' | 'incoming' | 'connected';
    targetUser?: string;
  }>({ type: 'idle' });
  const [callDuration, setCallDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);

  // Call-related refs for WebRTC and media streams
  const localStreamRef = useRef<MediaStream | null>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const channelRef = useRef<any>(null);
  const iceCandidatesBuffer = useRef<any[]>([]);
  const callTimerRef = useRef<any>(null);
  const dialingTimeoutRef = useRef<any>(null);

  // A ref to keep the latest callState accessible inside event listeners (avoids stale closure)
  const callStateRef = useRef(callState);
  useEffect(() => {
    callStateRef.current = callState;
  }, [callState]);

  // Clean up all call resources (Safety Guard 3: Stop media tracks & close peer connections)
  const cleanupCall = () => {
    if (dialingTimeoutRef.current) {
      clearTimeout(dialingTimeoutRef.current);
      dialingTimeoutRef.current = null;
    }

    if (callTimerRef.current) {
      clearInterval(callTimerRef.current);
      callTimerRef.current = null;
    }

    // Stop synthesized audio
    audioManager.stopAll();

    // Stop microphone tracks
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track) => {
        console.log('Stopping microphone track:', track.label);
        track.stop();
      });
      localStreamRef.current = null;
    }

    // Close WebRTC peer connection
    if (peerConnectionRef.current) {
      console.log('Closing RTCPeerConnection');
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }

    // Remove dynamically created remote audio elements
    const audioEl = document.getElementById('remote-audio-element') as HTMLAudioElement;
    if (audioEl) {
      audioEl.srcObject = null;
      audioEl.remove();
    }

    setCallState({ type: 'idle' });
    setCallDuration(0);
    setIsMuted(false);
    iceCandidatesBuffer.current = [];
  };

  // Helper to send a signaling message over Supabase Broadcast
  const sendCallSignal = (data: any) => {
    if (channelRef.current) {
      channelRef.current.send({
        type: 'broadcast',
        event: 'call-signal',
        payload: {
          ...data,
          targetUser: data.receiver // Duplicate receiver into targetUser for filtering safety
        }
      });
    }
  };

  // WebRTC Setup: Initialize media stream & RTCPeerConnection
  const startWebRTCConnection = async (peerEmail: string, isInitiator: boolean) => {
    try {
      // Request mic permission
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      localStreamRef.current = stream;

      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' },
        ],
      });
      peerConnectionRef.current = pc;

      // Add local audio tracks to the connection
      stream.getTracks().forEach((track) => pc.addTrack(track, stream));

      // ICE Candidates gathering callback
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          sendCallSignal({
            type: 'webrtc-ice',
            sender: userEmail,
            receiver: peerEmail,
            candidate: event.candidate,
          });
        }
      };

      // Play the remote stream when it is received
      pc.ontrack = (event) => {
        console.log('Received remote track', event.streams[0]);
        const remoteStream = event.streams[0];
        let audioEl = document.getElementById('remote-audio-element') as HTMLAudioElement;
        if (!audioEl) {
          audioEl = document.createElement('audio');
          audioEl.id = 'remote-audio-element';
          audioEl.autoplay = true;
          document.body.appendChild(audioEl);
        }
        audioEl.srcObject = remoteStream;
      };

      // If we are the call initiator, we create and send the SDP Offer
      if (isInitiator) {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        sendCallSignal({
          type: 'webrtc-offer',
          sender: userEmail,
          receiver: peerEmail,
          sdp: offer,
        });
      }
    } catch (err) {
      console.error('Failed to setup WebRTC connection:', err);
      alert('마이크 권한이 필요합니다. 브라우저 설정에서 마이크 액세스를 권한을 허용해 주세요.');
      hangUpCall();
    }
  };

  // Process incoming WebRTC Offers
  const handleWebRTCOffer = async (offerSdp: any, peerEmail: string) => {
    try {
      if (!peerConnectionRef.current) {
        // Request microphone and build peer connection
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        localStreamRef.current = stream;

        const pc = new RTCPeerConnection({
          iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
          ],
        });
        peerConnectionRef.current = pc;

        stream.getTracks().forEach((track) => pc.addTrack(track, stream));

        pc.onicecandidate = (event) => {
          if (event.candidate) {
            sendCallSignal({
              type: 'webrtc-ice',
              sender: userEmail,
              receiver: peerEmail,
              candidate: event.candidate,
            });
          }
        };

        pc.ontrack = (event) => {
          console.log('Received remote track (callee)', event.streams[0]);
          const remoteStream = event.streams[0];
          let audioEl = document.getElementById('remote-audio-element') as HTMLAudioElement;
          if (!audioEl) {
            audioEl = document.createElement('audio');
            audioEl.id = 'remote-audio-element';
            audioEl.autoplay = true;
            document.body.appendChild(audioEl);
          }
          audioEl.srcObject = remoteStream;
        };
      }

      const pc = peerConnectionRef.current;
      await pc.setRemoteDescription(new RTCSessionDescription(offerSdp));

      // Process any buffered ICE candidates that arrived before the offer description
      while (iceCandidatesBuffer.current.length > 0) {
        const cand = iceCandidatesBuffer.current.shift();
        if (cand) {
          await pc.addIceCandidate(new RTCIceCandidate(cand));
        }
      }

      // Generate SDP Answer
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      sendCallSignal({
        type: 'webrtc-answer',
        sender: userEmail,
        receiver: peerEmail,
        sdp: answer,
      });

      setCallState({ type: 'connected', targetUser: peerEmail });
    } catch (err) {
      console.error('Failed to handle WebRTC offer:', err);
      hangUpCall();
    }
  };

  // Main Call Signaling handler
  const handleCallSignal = async (payload: any) => {
    // Safety Guard 1: Target Filtering - Only process signals targeting this client
    if (payload.targetUser !== userEmail) return;

    console.log('Received signal:', payload.type, payload);

    switch (payload.type) {
      case 'call-invite':
        // If we are already busy in another call, reject with 'busy' status
        if (callStateRef.current.type !== 'idle') {
          sendCallSignal({
            type: 'call-busy',
            sender: userEmail,
            receiver: payload.sender,
          });
          return;
        }
        setCallState({ type: 'incoming', targetUser: payload.sender });
        audioManager.playIncoming();
        break;

      case 'call-accept':
        if (callStateRef.current.type === 'dialing') {
          audioManager.stopAll();
          audioManager.playSuccess();
          if (dialingTimeoutRef.current) {
            clearTimeout(dialingTimeoutRef.current);
            dialingTimeoutRef.current = null;
          }
          setCallState({ type: 'connected', targetUser: payload.sender });
          await startWebRTCConnection(payload.sender, true);
        }
        break;

      case 'call-decline':
        if (callStateRef.current.type === 'dialing') {
          audioManager.stopAll();
          alert(`${getCompanyId(payload.sender)}님이 전화를 거절하였습니다.`);
          cleanupCall();
        }
        break;

      case 'call-busy':
        if (callStateRef.current.type === 'dialing') {
          audioManager.stopAll();
          alert(`${getCompanyId(payload.sender)}님은 현재 통화 중입니다.`);
          cleanupCall();
        }
        break;

      case 'call-cancel':
        if (callStateRef.current.type === 'incoming' && callStateRef.current.targetUser === payload.sender) {
          audioManager.stopAll();
          cleanupCall();
        }
        break;

      case 'webrtc-offer':
        if (callStateRef.current.type === 'incoming' || callStateRef.current.type === 'connected') {
          await handleWebRTCOffer(payload.sdp, payload.sender);
        }
        break;

      case 'webrtc-answer':
        if (peerConnectionRef.current) {
          await peerConnectionRef.current.setRemoteDescription(new RTCSessionDescription(payload.sdp));
          while (iceCandidatesBuffer.current.length > 0) {
            const cand = iceCandidatesBuffer.current.shift();
            if (cand) {
              await peerConnectionRef.current.addIceCandidate(new RTCIceCandidate(cand));
            }
          }
        }
        break;

      case 'webrtc-ice':
        if (peerConnectionRef.current) {
          if (peerConnectionRef.current.remoteDescription) {
            await peerConnectionRef.current.addIceCandidate(new RTCIceCandidate(payload.candidate));
          } else {
            iceCandidatesBuffer.current.push(payload.candidate);
          }
        }
        break;

      case 'call-hungup':
        if (callStateRef.current.type !== 'idle') {
          audioManager.playEnd();
          cleanupCall();
        }
        break;

      default:
        break;
    }
  };

  // Keep a ref to the latest call signal handler for the realtime broadcast listener
  const handleCallSignalRef = useRef(handleCallSignal);
  useEffect(() => {
    handleCallSignalRef.current = handleCallSignal;
  });

  // Call duration timer trigger
  useEffect(() => {
    if (callState.type === 'connected') {
      // Ensure all dialing/incoming ringtones are silenced immediately when call connects
      audioManager.stopAll();
      audioManager.playSuccess();

      setCallDuration(0);
      callTimerRef.current = setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    } else {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
        callTimerRef.current = null;
      }
    }
    return () => {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
      }
    };
  }, [callState.type]);

  // Fetch history & Setup Supabase Realtime channel
  useEffect(() => {
    const fetchChatHistory = async () => {
      try {
        const { data, error } = await supabase
          .from('messages')
          .select('*')
          .order('created_at', { ascending: true });

        if (error) throw error;
        if (data) {
          setMessages(data);
        }
      } catch (err) {
        console.error('Error fetching chat history:', err);
      } finally {
        setLoadingHistory(false);
      }
    };

    fetchChatHistory();

    // Setup channel with Presence and Postgres Changes
    const channel = supabase.channel('messages_realtime', {
      config: {
        presence: {
          key: userEmail,
        },
      },
    });
    channelRef.current = channel;

    channel
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
        },
        (payload) => {
          const newMsg = payload.new as DBMessage;
          setMessages((prev) => {
            if (prev.some((msg) => msg.id === newMsg.id)) {
              return prev;
            }
            return [...prev, newMsg];
          });
        }
      )
      .on('presence', { event: 'sync' }, () => {
        const state = channel.presenceState();
        // Sync active user list excluding ourselves
        const emails = Object.keys(state).filter(email => email !== userEmail);
        setOnlineUsers(emails);
      })
      .on('presence', { event: 'join' }, ({ key }) => {
        if (key && key !== userEmail) {
          const name = getCompanyId(key);
          setJoinNotice(`${name}님이 입장했습니다.`);
          setTimeout(() => setJoinNotice((prev) => (prev?.includes(name) ? null : prev)), 3500);
        }
      })
      .on('presence', { event: 'leave' }, ({ key }) => {
        if (key && key !== userEmail) {
          const name = getCompanyId(key);
          setJoinNotice(`${name}님이 퇴장했습니다.`);
          setTimeout(() => setJoinNotice((prev) => (prev?.includes(name) ? null : prev)), 3500);
        }
      })
      .on('broadcast', { event: 'call-signal' }, ({ payload }) => {
        handleCallSignalRef.current(payload);
      });

    channel.subscribe(async (status) => {
      if (status === 'SUBSCRIBED') {
        // Safety Guard 2: Presence state broadcasting (track)
        await channel.track({
          userEmail: userEmail,
          online_at: new Date().toISOString()
        });
      }
    });

    return () => {
      cleanupCall();
      supabase.removeChannel(channel);
    };
  }, [userEmail]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSignOut = async () => {
    try {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    } catch (err) {
      console.error('Error signing out:', err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    const textToSend = inputText.trim();
    setInputText('');

    try {
      const { error } = await supabase
        .from('messages')
        .insert([
          {
            sender: userEmail,
            text: textToSend,
          },
        ]);

      if (error) throw error;
    } catch (err) {
      console.error('Error saving message to Supabase:', err);
      setInputText(textToSend);
    }
  };

  const formatTimestamp = (dateStr: string): string => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      return d.toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
    } catch {
      return '';
    }
  };

  // Format active call duration timer (e.g. 01:23)
  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Start outgoing call
  const initiateCall = (targetEmail: string) => {
    if (targetEmail === userEmail) return;

    setShowUserListModal(false);
    setCallState({ type: 'dialing', targetUser: targetEmail });
    audioManager.playDialing();

    // Transmit invitation
    sendCallSignal({
      type: 'call-invite',
      sender: userEmail,
      receiver: targetEmail,
    });

    // Automatically expire dialing after 30 seconds of ringing
    dialingTimeoutRef.current = setTimeout(() => {
      audioManager.stopAll();
      alert('상대방이 전화를 받지 않습니다.');
      cancelCall(targetEmail);
    }, 30000);
  };

  // Cancel outgoing call
  const cancelCall = (targetEmail: string) => {
    sendCallSignal({
      type: 'call-cancel',
      sender: userEmail,
      receiver: targetEmail,
    });
    audioManager.stopAll();
    cleanupCall();
  };

  // Accept incoming call
  const acceptCall = async () => {
    const callerEmail = callState.targetUser;
    if (!callerEmail) return;

    audioManager.stopAll();
    audioManager.playSuccess();
    setCallState({ type: 'connected', targetUser: callerEmail });

    sendCallSignal({
      type: 'call-accept',
      sender: userEmail,
      receiver: callerEmail,
    });

    await startWebRTCConnection(callerEmail, false);
  };

  // Decline incoming call
  const declineCall = () => {
    const callerEmail = callState.targetUser;
    if (callerEmail) {
      sendCallSignal({
        type: 'call-decline',
        sender: userEmail,
        receiver: callerEmail,
      });
    }
    audioManager.stopAll();
    cleanupCall();
  };

  // Hang up active call
  const hangUpCall = () => {
    const peerEmail = callState.targetUser;
    if (peerEmail) {
      sendCallSignal({
        type: 'call-hungup',
        sender: userEmail,
        receiver: peerEmail,
      });
    }
    audioManager.playEnd();
    cleanupCall();
  };

  // Toggle microphone mute status
  const toggleMute = () => {
    if (localStreamRef.current) {
      const audioTrack = localStreamRef.current.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        setIsMuted(!audioTrack.enabled);
      }
    }
  };

  return (
    <div style={styles.container} className="animate-fade-in">
      {/* Participant Sidebar */}
      {showSidebar && (
        <div style={styles.sidebar} className="glass-panel animate-fade-in">
          <div style={styles.sidebarHeader}>
            <div style={styles.sidebarTitle}>
              <span>👥 접속 임직원</span>
              <span style={styles.onlineCountBadge}>{onlineUsers.length + 1}명</span>
            </div>
          </div>

          <div style={styles.sidebarUserList}>
            {/* My profile */}
            <div style={styles.myUserCard}>
              <span style={styles.myAvatar}>🛡️</span>
              <div style={styles.myInfo}>
                <div style={styles.myNameRow}>
                  <span style={styles.userName}>{currentCompanyId}</span>
                  <span style={styles.meBadge}>나</span>
                </div>
                <span style={styles.onlineText}>🟢 온라인</span>
              </div>
            </div>

            <div style={styles.sidebarSectionTitle}>
              대화 참여자 ({onlineUsers.length})
            </div>

            {onlineUsers.length === 0 ? (
              <div style={styles.sidebarEmpty}>
                <span>현재 접속 중인 다른 동료가 없습니다.</span>
                <span style={styles.sidebarEmptyTip}>새 창이나 탭에서 로그인해 보세요!</span>
              </div>
            ) : (
              onlineUsers.map((email) => {
                const name = getCompanyId(email);
                return (
                  <div key={email} style={styles.participantItem} className="animate-fade-in">
                    <div style={styles.participantInfo}>
                      <span className="badge-online"></span>
                      <span style={styles.participantName}>{name}</span>
                    </div>
                    <button
                      onClick={() => initiateCall(email)}
                      style={styles.sidebarCallBtn}
                      title={`${name}님에게 1:1 음성 통화 걸기`}
                      disabled={callState.type !== 'idle'}
                    >
                      📞 통화
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      <div style={styles.chatWrapper} className="glass-panel">
        
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerInfo}>
            <span className="badge-online"></span>
            <div>
              <h2 style={styles.headerTitle}>Official Private Chat</h2>
              <p style={styles.headerSubtitle}>보안망 가동 중 | 임직원 전용 메신저</p>
            </div>
          </div>
          
          <div style={styles.headerActions}>
            {/* Sidebar toggle button */}
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              style={{
                ...styles.toggleSidebarBtn,
                background: showSidebar ? 'rgba(37, 99, 235, 0.1)' : 'var(--bg-app)',
                color: showSidebar ? 'var(--primary)' : 'var(--text-secondary)',
              }}
              title="접속자 목록 열기/닫기"
            >
              👥 접속자 ({onlineUsers.length + 1})
            </button>

            <div style={styles.userInfo}>
              <span style={styles.userIcon}>🛡️</span>
              <span style={styles.userEmail}>{currentCompanyId}</span>
            </div>
            
            {/* Telephone Icon (Starts a call) */}
            <button 
              onClick={() => setShowUserListModal(true)} 
              style={styles.phoneBtn}
              title="임직원 실시간 음성 통화"
            >
              📞
            </button>

            <button onClick={handleSignOut} style={styles.signOutBtn} className="btn-secondary">
              보안 로그아웃
            </button>
          </div>
        </div>

        {/* Join / Leave notification banner */}
        {joinNotice && (
          <div style={styles.joinToast} className="animate-fade-in">
            <span>✨ {joinNotice}</span>
          </div>
        )}

        {/* Call Banner - Floating at the top of the message list when call is connected */}
        {callState.type === 'connected' && callState.targetUser && (
          <div style={styles.callBar} className="animate-fade-in">
            <div style={styles.callBarInfo}>
              <span className="call-timer-dot"></span>
              <span style={styles.callBarText}>
                통화 연결됨: <strong>{getCompanyId(callState.targetUser)}</strong>
              </span>
              <span style={styles.callBarTimer}>{formatDuration(callDuration)}</span>
            </div>
            <div style={styles.callBarControls}>
              <button 
                onClick={toggleMute} 
                style={{
                  ...styles.callMuteBtn,
                  background: isMuted ? '#ef4444' : '#f3f4f6',
                  color: isMuted ? '#ffffff' : '#374151',
                  borderColor: isMuted ? '#dc2626' : '#d1d5db',
                }}
              >
                {isMuted ? '🔇 마이크 켜기' : '🎙️ 음소거'}
              </button>
              <button onClick={hangUpCall} style={styles.callHangUpBtn}>
                ☎️ 통화 종료
              </button>
            </div>
          </div>
        )}

        {/* Message Panel */}
        <div style={styles.messagePanel}>
          {loadingHistory ? (
            <div style={styles.loadingWrapper}>
              <div style={styles.loadingSpinner}></div>
              <span style={styles.loadingText}>메시지 이력을 불러오고 있습니다...</span>
            </div>
          ) : messages.length === 0 ? (
            <div style={styles.emptyMessages}>
              <span>보안 대화방에 첫 메시지를 남겨보세요.</span>
            </div>
          ) : (
            <div style={styles.messagesList}>
              {messages.map((msg) => {
                const isMe = msg.sender === userEmail;
                const cleanSender = getCompanyId(msg.sender);
                
                return (
                  <div
                    key={msg.id}
                    style={{
                      ...styles.messageWrapper,
                      justifyContent: isMe ? 'flex-end' : 'flex-start',
                    }}
                    className="animate-slide-in"
                  >
                    <div
                      style={{
                        ...styles.messageContainer,
                        alignItems: isMe ? 'flex-end' : 'flex-start',
                      }}
                    >
                      <span style={styles.senderName}>{cleanSender}</span>

                      <div
                        style={{
                          ...styles.bubbleWrapper,
                          flexDirection: isMe ? 'row-reverse' : 'row',
                        }}
                      >
                        <div
                          style={{
                            ...styles.bubble,
                            background: isMe ? 'var(--primary)' : '#e5e7eb',
                            color: isMe ? '#ffffff' : 'var(--text-primary)',
                            borderRadius: isMe 
                              ? '14px 14px 2px 14px' 
                              : '14px 14px 14px 2px',
                          }}
                        >
                          <p style={styles.messageText}>{msg.text}</p>
                        </div>
                        <span style={styles.timestamp}>{formatTimestamp(msg.created_at)}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Form */}
        <form onSubmit={handleSendMessage} style={styles.inputForm}>
          <input
            type="text"
            placeholder="메시지를 입력하세요..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            style={styles.chatInput}
          />
          <button type="submit" className="btn-primary" style={styles.sendBtn}>
            전송
          </button>
        </form>

      </div>

      {/* MODAL 1: Choose online user to call */}
      {showUserListModal && (
        <div className="call-modal-overlay">
          <div className="call-modal-content">
            <h3 style={styles.modalTitle}>임직원 통화 연결</h3>
            <p style={styles.modalSubtitle}>현재 온라인인 임직원을 선택하여 전화를 겁니다.</p>
            
            <div style={styles.userListContainer}>
              {onlineUsers.length === 0 ? (
                <div style={styles.emptyListText}>현재 접속 중인 다른 임직원이 없습니다.</div>
              ) : (
                onlineUsers.map((email) => (
                  <div key={email} className="call-user-item">
                    <span style={styles.userName}>{getCompanyId(email)}</span>
                    <button 
                      onClick={() => initiateCall(email)} 
                      className="btn-primary"
                      style={styles.dialUserBtn}
                    >
                      📞 연결
                    </button>
                  </div>
                ))
              )}
            </div>

            <button 
              onClick={() => setShowUserListModal(false)} 
              className="btn-secondary"
              style={styles.modalCloseBtn}
            >
              닫기
            </button>
          </div>
        </div>
      )}

      {/* MODAL 2: Outgoing Call Dialing Modal */}
      {callState.type === 'dialing' && callState.targetUser && (
        <div className="call-modal-overlay">
          <div className="call-modal-content">
            <div className="pulse-ring-blue">📞</div>
            <h3 style={styles.modalTitle}>{getCompanyId(callState.targetUser)}님에게</h3>
            <p style={styles.modalStatusText}>전화를 거는 중...</p>
            <p style={styles.modalConnectingText}>보안 통신망을 설정하고 있습니다. 통화 연결음 재생 중...</p>
            
            <button 
              onClick={() => cancelCall(callState.targetUser!)} 
              className="btn-secondary"
              style={styles.hangUpModalBtn}
            >
              통화 취소
            </button>
          </div>
        </div>
      )}

      {/* MODAL 3: Incoming Call Modal */}
      {callState.type === 'incoming' && callState.targetUser && (
        <div className="call-modal-overlay">
          <div className="call-modal-content">
            <div className="pulse-ring-green">🔔</div>
            <h3 style={styles.modalTitle}>{getCompanyId(callState.targetUser)}</h3>
            <p style={styles.modalStatusText}>전화 수신 중...</p>
            <p style={styles.modalConnectingText}>보안 음성 통화 요청이 들어왔습니다.</p>
            
            <div style={styles.callResponseControls}>
              <button 
                onClick={acceptCall} 
                className="btn-primary"
                style={styles.acceptCallBtn}
              >
                📞 수락
              </button>
              <button 
                onClick={declineCall} 
                className="btn-secondary"
                style={styles.declineCallBtn}
              >
                ❌ 거절
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    width: '100%',
    maxWidth: '1080px',
    height: '85vh',
    padding: '16px',
    display: 'flex',
    gap: '16px',
  },
  sidebar: {
    width: '260px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    flexShrink: 0,
    background: '#ffffff',
  },
  sidebarHeader: {
    padding: '16px 18px',
    borderBottom: '1px solid var(--border-color)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: '#fafafa',
  },
  sidebarTitle: {
    fontSize: '0.95rem',
    fontWeight: '700',
    color: 'var(--text-primary)',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    width: '100%',
    justifyContent: 'space-between',
  },
  onlineCountBadge: {
    background: 'rgba(16, 185, 129, 0.12)',
    color: '#059669',
    fontSize: '0.75rem',
    fontWeight: '700',
    padding: '2px 8px',
    borderRadius: '12px',
  },
  sidebarUserList: {
    flex: 1,
    overflowY: 'auto',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  myUserCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '10px 12px',
    background: 'rgba(37, 99, 235, 0.05)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid rgba(37, 99, 235, 0.15)',
  },
  myAvatar: {
    fontSize: '1.2rem',
  },
  myInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    overflow: 'hidden',
  },
  myNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  meBadge: {
    fontSize: '0.68rem',
    background: 'var(--primary)',
    color: '#ffffff',
    padding: '1px 5px',
    borderRadius: '4px',
    fontWeight: '600',
  },
  onlineText: {
    fontSize: '0.72rem',
    color: '#059669',
    fontWeight: '500',
  },
  sidebarSectionTitle: {
    fontSize: '0.78rem',
    color: 'var(--text-secondary)',
    fontWeight: '600',
    padding: '8px 4px 4px 4px',
  },
  participantItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-color)',
    background: 'var(--bg-hover)',
    gap: '6px',
  },
  participantInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    overflow: 'hidden',
    flex: 1,
  },
  participantName: {
    fontSize: '0.86rem',
    fontWeight: '600',
    color: 'var(--text-primary)',
    textOverflow: 'ellipsis',
    overflow: 'hidden',
    whiteSpace: 'nowrap',
  },
  sidebarCallBtn: {
    padding: '4px 10px',
    fontSize: '0.78rem',
    borderRadius: '14px',
    background: '#10b981',
    color: '#ffffff',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '600',
    flexShrink: 0,
  },
  sidebarEmpty: {
    padding: '24px 8px',
    textAlign: 'center',
    color: 'var(--text-muted)',
    fontSize: '0.82rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    lineHeight: '1.4',
  },
  sidebarEmptyTip: {
    fontSize: '0.72rem',
    color: 'var(--text-secondary)',
  },
  toggleSidebarBtn: {
    padding: '6px 12px',
    fontSize: '0.82rem',
    borderRadius: '20px',
    border: '1px solid var(--border-color)',
    cursor: 'pointer',
    fontWeight: '600',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'all 0.15s ease',
  },
  joinToast: {
    position: 'absolute',
    top: '72px',
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(17, 24, 39, 0.88)',
    color: '#ffffff',
    padding: '8px 18px',
    borderRadius: '20px',
    fontSize: '0.85rem',
    fontWeight: '500',
    zIndex: 100,
    pointerEvents: 'none',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
  },
  chatWrapper: {
    flex: 1,
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    position: 'relative',
  },
  header: {
    padding: '16px 24px',
    borderBottom: '1px solid var(--border-color)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    background: '#ffffff',
  },
  headerInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    textAlign: 'left',
  },
  headerTitle: {
    fontSize: '1.2rem',
    fontWeight: '700',
    color: 'var(--text-primary)',
    margin: 0,
  },
  headerSubtitle: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    margin: 0,
  },
  headerActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  userInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 12px',
    background: 'var(--bg-app)',
    borderRadius: '20px',
    border: '1px solid var(--border-color)',
  },
  userIcon: {
    fontSize: '0.9rem',
  },
  userEmail: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    fontWeight: '600',
  },
  phoneBtn: {
    padding: '8px 12px',
    fontSize: '1rem',
    borderRadius: '20px',
    background: 'rgba(37, 99, 235, 0.08)',
    border: '1px solid rgba(37, 99, 235, 0.15)',
    color: 'var(--primary)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
  },
  signOutBtn: {
    padding: '6px 12px',
    fontSize: '0.85rem',
    borderRadius: '20px',
  },
  callBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 24px',
    background: '#eff6ff',
    borderBottom: '1px solid #bfdbfe',
    zIndex: 10,
  },
  callBarInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  callBarText: {
    fontSize: '0.92rem',
    color: '#1e40af',
  },
  callBarTimer: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#1d4ed8',
    background: '#dbeafe',
    padding: '2px 8px',
    borderRadius: '12px',
  },
  callBarControls: {
    display: 'flex',
    gap: '8px',
  },
  callMuteBtn: {
    padding: '6px 14px',
    fontSize: '0.85rem',
    borderRadius: '6px',
    border: '1px solid',
    cursor: 'pointer',
    fontWeight: '500',
  },
  callHangUpBtn: {
    padding: '6px 14px',
    fontSize: '0.85rem',
    borderRadius: '6px',
    background: '#ef4444',
    color: '#ffffff',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '600',
  },
  messagePanel: {
    flex: 1,
    overflowY: 'auto',
    padding: '24px',
    background: '#f9fafb',
    display: 'flex',
    flexDirection: 'column',
  },
  loadingWrapper: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    flex: 1,
  },
  loadingSpinner: {
    width: '32px',
    height: '32px',
    border: '3px solid rgba(37, 99, 235, 0.15)',
    borderRadius: '50%',
    borderTopColor: 'var(--primary)',
    animation: 'spin 1s ease-in-out infinite',
  },
  loadingText: {
    fontSize: '0.88rem',
    color: 'var(--text-secondary)',
  },
  emptyMessages: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    flex: 1,
    color: 'var(--text-secondary)',
    fontSize: '0.9rem',
  },
  messagesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '18px',
  },
  messageWrapper: {
    display: 'flex',
    width: '100%',
  },
  messageContainer: {
    display: 'flex',
    flexDirection: 'column',
    maxWidth: '70%',
    gap: '4px',
  },
  senderName: {
    fontSize: '0.8rem',
    color: 'var(--text-secondary)',
    fontWeight: '600',
    paddingLeft: '2px',
    paddingRight: '2px',
  },
  bubbleWrapper: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '6px',
  },
  bubble: {
    padding: '10px 14px',
    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
  },
  messageText: {
    fontSize: '0.92rem',
    lineHeight: '1.45',
    textAlign: 'left',
    wordBreak: 'break-all',
    whiteSpace: 'pre-wrap',
  },
  timestamp: {
    fontSize: '0.7rem',
    color: 'var(--text-secondary)',
    flexShrink: 0,
  },
  inputForm: {
    padding: '16px 24px',
    borderTop: '1px solid var(--border-color)',
    background: '#ffffff',
    display: 'flex',
    gap: '12px',
    alignItems: 'center',
  },
  chatInput: {
    flex: 1,
    borderRadius: '6px',
  },
  sendBtn: {
    padding: '10px 20px',
    borderRadius: '6px',
  },
  modalTitle: {
    fontSize: '1.25rem',
    fontWeight: '700',
    color: 'var(--text-primary)',
    marginBottom: '8px',
  },
  modalSubtitle: {
    fontSize: '0.88rem',
    color: 'var(--text-secondary)',
    marginBottom: '20px',
  },
  modalStatusText: {
    fontSize: '1.1rem',
    fontWeight: '600',
    color: 'var(--text-primary)',
    marginBottom: '8px',
  },
  modalConnectingText: {
    fontSize: '0.85rem',
    color: 'var(--text-secondary)',
    marginBottom: '24px',
    lineHeight: '1.4',
  },
  userListContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    maxHeight: '200px',
    overflowY: 'auto',
    marginBottom: '20px',
    paddingRight: '4px',
  },
  userName: {
    fontSize: '0.92rem',
    fontWeight: '600',
    color: 'var(--text-primary)',
  },
  dialUserBtn: {
    padding: '6px 12px',
    fontSize: '0.85rem',
    borderRadius: '6px',
  },
  emptyListText: {
    fontSize: '0.88rem',
    color: 'var(--text-secondary)',
    padding: '20px 0',
  },
  modalCloseBtn: {
    width: '100%',
    padding: '10px',
    borderRadius: '6px',
  },
  hangUpModalBtn: {
    width: '100%',
    padding: '10px',
    borderRadius: '6px',
    background: '#ef4444',
    color: '#ffffff',
    border: 'none',
  },
  callResponseControls: {
    display: 'flex',
    gap: '12px',
    justifyContent: 'center',
  },
  acceptCallBtn: {
    flex: 1,
    padding: '12px',
    borderRadius: '6px',
    background: '#10b981',
    color: '#ffffff',
  },
  declineCallBtn: {
    flex: 1,
    padding: '12px',
    borderRadius: '6px',
    background: '#ef4444',
    color: '#ffffff',
    border: 'none',
  },
};
