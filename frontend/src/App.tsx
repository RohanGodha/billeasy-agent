import { useEffect, useState } from 'react';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { api, getToken, setToken } from './lib/api';
import { ErrorBoundary } from './components/ErrorBoundary';

export default function App() {
  const [authed, setAuthed] = useState<boolean>(false);
  const [checking, setChecking] = useState<boolean>(true);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      setChecking(false);
      return;
    }
    // soft-validate by pinging /status (uses token)
    api
      .status()
      .then(() => setAuthed(true))
      .catch(() => {
        setToken(null);
        setAuthed(false);
      })
      .finally(() => setChecking(false));
  }, []);

  if (checking) {
    return (
      <div className="h-full flex items-center justify-center text-text-muted text-sm">
        <span className="animate-pulse-dot">●</span>&nbsp;Initialising…
      </div>
    );
  }

  return (
    <ErrorBoundary>
      {authed ? <Dashboard onLogout={() => { setToken(null); setAuthed(false); }} />
              : <Login onAuth={() => setAuthed(true)} />}
    </ErrorBoundary>
  );
}
