import type { ControlEvent } from './types';

function wsUrl(path: string, token: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}${path}?token=${encodeURIComponent(token)}`;
}

export function openScreenSocket(
  token: string,
  onFrame: (blob: Blob) => void,
  onClose: () => void,
  onError: () => void,
): WebSocket {
  const ws = new WebSocket(wsUrl('/ws/screen', token));
  ws.binaryType = 'blob';
  ws.onmessage = (event) => {
    if (event.data instanceof Blob) onFrame(event.data);
  };
  ws.onclose = onClose;
  ws.onerror = onError;
  return ws;
}

export function openControlSocket(
  token: string,
  onMessage: (event: ControlEvent) => void,
  onClose: () => void,
): WebSocket {
  const ws = new WebSocket(wsUrl('/ws/control', token));
  ws.onmessage = (event) => onMessage(JSON.parse(event.data) as ControlEvent);
  ws.onclose = onClose;
  return ws;
}

