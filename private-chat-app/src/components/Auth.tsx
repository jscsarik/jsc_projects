import React, { useState } from 'react';
import { supabase } from '../lib/supabaseClient';

export const Auth: React.FC = () => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [companyId, setCompanyId] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const getFriendlyErrorMessage = (error: any): string => {
    if (!error) return '알 수 없는 오류가 발생했습니다.';
    const msg = error.message || String(error);
    
    // Map Supabase auth errors to friendly Korean messages
    if (msg.includes('Invalid login credentials')) {
      return '사내 ID 또는 비밀번호가 일치하지 않습니다.';
    }
    if (msg.includes('User already registered') || msg.includes('already registered')) {
      return '이미 등록된 사내 ID입니다.';
    }
    if (msg.includes('Password should be at least 6 characters') || msg.includes('Password should be at least')) {
      return '비밀번호는 보안을 위해 최소 6자 이상이어야 합니다.';
    }
    if (msg.includes('rate limit') || msg.includes('over_email_send_rate_limit')) {
      return '요청 횟수 제한을 초과했습니다. 잠시 후 다시 시도해 주세요.';
    }
    if (msg.includes('Signups not allowed') || msg.includes('signups are disabled')) {
      return 'Supabase에서 신규 회원가입이 비활성화되어 있습니다. (Supabase Auth 설정을 확인하세요)';
    }
    if (msg.includes('fetch failed') || msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('ENOTFOUND')) {
      return 'Supabase 서버에 연결할 수 없습니다. 무료 플랜 일시정지(Paused) 상태이거나 .env 설정을 확인해 주세요.';
    }
    
    return `인증 오류가 발생했습니다: ${msg}`;
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    const trimmedId = companyId.trim();

    // ID validation
    if (!trimmedId || !password.trim()) {
      setErrorMsg('사내 ID와 비밀번호를 모두 입력해 주세요.');
      setLoading(false);
      return;
    }

    // Check if ID contains invalid email characters or is format-incompatible
    const idRegex = /^[a-zA-Z0-9_.-]+$/;
    if (!idRegex.test(trimmedId)) {
      setErrorMsg('사내 ID는 영문, 숫자, 밑줄(_), 하이픈(-), 마침표(.)만 사용할 수 있습니다.');
      setLoading(false);
      return;
    }

    // Automatically append corporate fake domain to form valid email syntax for Supabase Auth
    const email = `${trimmedId}@official-chat.com`;

    try {
      if (isSignUp) {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
        });

        if (error) throw error;

        if (data.user && data.session === null) {
          setSuccessMsg('신규 계정 신청이 전송되었습니다. 관리자 승인 후 사용 가능합니다.');
        } else {
          setSuccessMsg('신규 계정 등록이 완료되었습니다. 로그인해 주십시오.');
          setIsSignUp(false);
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });

        if (error) throw error;
      }
    } catch (err: any) {
      console.error('Corporate Auth Error:', err);
      setErrorMsg(getFriendlyErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container} className="animate-fade-in">
      <div style={styles.card} className="glass-panel">
        <div style={styles.header}>
          <div style={styles.logoContainer}>
            <span style={styles.logoIcon}>🛡️</span>
            <h2 style={styles.title}>Official Private Chat</h2>
          </div>
          <p style={styles.subtitle}>
            {isSignUp 
              ? '업무 통신을 위해 신규 계정을 생성합니다.' 
              : '사내 보안 통신망 및 기밀 유지를 위한 공식 비공개 메신저망'}
          </p>
        </div>

        {errorMsg && (
          <div style={styles.errorAlert} className="animate-fade-in">
            <span style={styles.alertIcon}>⚠️</span>
            <span style={styles.errorText}>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div style={styles.successAlert} className="animate-fade-in">
            <span style={styles.alertIcon}>✅</span>
            <span style={styles.successText}>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleAuth} style={styles.form}>
          <div style={styles.inputGroup}>
            <label style={styles.label}>사내 ID (또는 사번)</label>
            <input
              type="text"
              placeholder="예: gildong.hong 또는 20260714"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              disabled={loading}
              style={styles.input}
              required
            />
          </div>

          <div style={styles.inputGroup}>
            <label style={styles.label}>비밀번호</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              style={styles.input}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={styles.submitBtn}
          >
            {loading ? (
              <span style={styles.spinner}></span>
            ) : isSignUp ? (
              '계정 등록하기'
            ) : (
              '보안 접속망 입장'
            )}
          </button>
        </form>

        <div style={styles.footer}>
          <p style={styles.footerText}>
            {isSignUp ? '이미 등록된 계정이 있으십니까?' : '처음 접속하십니까?'}
            <button
              onClick={() => {
                setIsSignUp(!isSignUp);
                setErrorMsg(null);
                setSuccessMsg(null);
              }}
              style={styles.switchBtn}
              type="button"
            >
              {isSignUp ? '로그인으로 전환' : '신규 계정 등록'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    width: '100%',
    maxWidth: '440px',
    padding: '20px',
  },
  card: {
    padding: '40px 32px',
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  },
  header: {
    textAlign: 'center',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  logoContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '10px',
    marginBottom: '4px',
  },
  logoIcon: {
    fontSize: '2rem',
  },
  title: {
    fontSize: '1.8rem',
    fontWeight: '800',
    color: 'var(--text-primary)',
    letterSpacing: '-0.5px',
  },
  subtitle: {
    fontSize: '0.9rem',
    color: 'var(--text-secondary)',
    lineHeight: '1.45',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  label: {
    fontSize: '0.85rem',
    fontWeight: '500',
    color: 'var(--text-secondary)',
    textAlign: 'left',
    paddingLeft: '4px',
  },
  input: {
    width: '100%',
  },
  submitBtn: {
    width: '100%',
    padding: '12px',
    marginTop: '8px',
    fontSize: '1rem',
    position: 'relative',
  },
  errorAlert: {
    background: '#fef2f2',
    border: '1px solid #fca5a5',
    borderRadius: 'var(--radius-sm)',
    padding: '12px 16px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    textAlign: 'left',
  },
  successAlert: {
    background: '#ecfdf5',
    border: '1px solid #a7f3d0',
    borderRadius: 'var(--radius-sm)',
    padding: '12px 16px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    textAlign: 'left',
  },
  alertIcon: {
    fontSize: '1.1rem',
    flexShrink: 0,
  },
  errorText: {
    fontSize: '0.85rem',
    color: '#991b1b',
    lineHeight: '1.4',
    fontWeight: '500',
  },
  successText: {
    fontSize: '0.85rem',
    color: '#065f46',
    lineHeight: '1.4',
    fontWeight: '500',
  },
  footer: {
    textAlign: 'center',
    marginTop: '8px',
  },
  footerText: {
    fontSize: '0.88rem',
    color: 'var(--text-secondary)',
  },
  switchBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--primary)',
    marginLeft: '6px',
    fontWeight: '600',
    fontSize: '0.88rem',
    textDecoration: 'underline',
    cursor: 'pointer',
    padding: 0,
  },
  spinner: {
    display: 'inline-block',
    width: '20px',
    height: '20px',
    border: '2px solid rgba(255, 255, 255, 0.3)',
    borderRadius: '50%',
    borderTopColor: '#ffffff',
    animation: 'spin 1s ease-in-out infinite',
  },
};
