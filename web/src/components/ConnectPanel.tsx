import { useState } from 'react';

interface Props {
  connecting: boolean;
  error: string | null;
  onConnect: (token: string) => void;
}

export function ConnectPanel({ connecting, error, onConnect }: Props) {
  const [token, setToken] = useState('');
  const [show, setShow] = useState(false);

  return (
    <div className="connect-panel">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onConnect(token.trim());
        }}
      >
        <h1 className="logo-lg">GEASS</h1>
        <div className="connect-token-row">
          <input
            type={show ? 'text' : 'password'}
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Token"
            autoFocus
            autoComplete="off"
          />
          <button
            type="button"
            className="token-eye"
            onClick={() => setShow((value) => !value)}
            aria-label={show ? '隐藏 Token' : '显示 Token'}
            title={show ? '隐藏 Token' : '显示 Token'}
          >
            {show ? '🙈' : '👁'}
          </button>
        </div>
        <button
          type="submit"
          className="btn-primary"
          disabled={connecting || !token.trim()}
        >
          {connecting ? 'CONNECTING…' : 'CONNECT'}
        </button>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}
