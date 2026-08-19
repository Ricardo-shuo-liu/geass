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
        <h1>Geass</h1>
        <p>请输入服务器控制台显示的访问 Token</p>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Token"
          autoFocus
          autoComplete="off"
        />
        <button type="submit" disabled={connecting || !token.trim()}>
          {connecting ? '连接中…' : '连接'}
        </button>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}

