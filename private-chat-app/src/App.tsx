import { useState, useEffect } from 'react';
import { supabase } from './lib/supabaseClient';
import type { Session } from '@supabase/supabase-js';
import { Auth } from './components/Auth';
import { Chat } from './components/Chat';

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check active session on initial load
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

    // Listen for authentication state changes (login, logout, token refresh, etc.)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  if (loading) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.spinner}></div>
        <p style={styles.loadingText}>보안 접속망 확인 중...</p>
      </div>
    );
  }

  return (
    <>
      {session ? (
        <Chat session={session} />
      ) : (
        <Auth />
      )}
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '16px',
    height: '100vh',
    width: '100%',
  },
  spinner: {
    width: '40px',
    height: '40px',
    border: '3px solid rgba(79, 70, 229, 0.15)',
    borderRadius: '50%',
    borderTopColor: 'var(--primary)',
    animation: 'spin 1s ease-in-out infinite',
  },
  loadingText: {
    fontSize: '0.95rem',
    color: 'var(--text-secondary)',
    fontWeight: '500',
    letterSpacing: '0.5px',
  },
};

export default App;
