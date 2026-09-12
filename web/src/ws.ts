import type { ControlEvent, ManualAction } from './types';

function wsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}${path}`;
}

export function openScreenSocket(
  token: string,
  onFrame: (blob: Blob) => void,
  onClose: (event: CloseEvent) => void,
  onError: () => void,
): WebSocket {
  // token 通过子协议传递，避免出现在 URL 与服务器日志中
  const ws = new WebSocket(wsUrl('/ws/screen'), ['geass', token]);
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
  onClose: (event: CloseEvent) => void,
): WebSocket {
  const ws = new WebSocket(wsUrl('/ws/control'), ['geass', token]);
  ws.onmessage = (event) => onMessage(JSON.parse(event.data) as ControlEvent);
  ws.onclose = onClose;
  return ws;
}

export function sendApproval(
  ws: WebSocket,
  id: string,
  approved: boolean,
): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'approval', id, approved }));
  }
}

export function sendManualInput(ws: WebSocket, action: ManualAction): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'manual_input', ...action }));
  }
}

export function sendActionDecision(
  ws: WebSocket,
  id: string,
  approved: boolean,
  target?: Record<string, unknown>,
): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'action_decision', id, approved, target }));
  }
}

export function sendPrivacyMask(
  ws: WebSocket,
  payload:
    | { action: 'add'; rect: { x: number; y: number; w: number; h: number } }
    | { action: 'remove'; id: string }
    | { action: 'clear' }
    | { action: 'enable' | 'disable' | 'toggle' },
): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'privacy_mask', ...payload }));
  }
}
