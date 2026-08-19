import { useState } from 'react';

interface Props {
  connecting: boolean;
  error: string | null;
  onConnect: (token: string) => void;
}

export function ConnectPanel({ connecting, error, onConnect }: Props) {
  const [token, setToken] = useState(localStorage.getItem('geass-token') ?? '');

  return (
    <div className="connect-panel">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onConnect(token.trim());
        }}
      >
        <h1 className="logo logo-lg">GEASS</h1>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Token"
          autoFocus
          autoComplete="off"
        />
        <button type="submit" className="btn-primary" disabled={connecting || !token.trim()}>
          {connecting ? 'CONNECTING…' : 'CONNECT'}
        </button>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}
