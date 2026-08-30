import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ControlEvent } from './types';
import {
  openControlSocket,
  openScreenSocket,
  sendApproval,
  sendManualInput,
} from './ws';

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;

  readyState = 1;
  binaryType = 'blob';
  url: string;
  protocols: string[];
  sent: string[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string, protocols?: string[]) {
    this.url = url;
    this.protocols = protocols ?? [];
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.instances = [];
});

function asFake(ws: WebSocket): FakeWebSocket {
  return ws as unknown as FakeWebSocket;
}

describe('ws', () => {
  it('opens the screen socket with the geass subprotocol', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);

    const ws = asFake(openScreenSocket('tok-1', () => {}, () => {}, () => {}));

    expect(ws.url.endsWith('/ws/screen')).toBe(true);
    expect(ws.protocols).toEqual(['geass', 'tok-1']);
  });

  it('delivers binary frames as blobs', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const frames: Blob[] = [];
    const ws = asFake(openScreenSocket('tok', (b) => frames.push(b), () => {}, () => {}));
    const blob = new Blob(['frame']);

    ws.onmessage?.({ data: blob } as MessageEvent);

    expect(frames).toEqual([blob]);
  });

  it('parses control events as JSON', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const events: ControlEvent[] = [];
    const ws = asFake(openControlSocket('tok', (event) => events.push(event), () => {}));

    ws.onmessage?.({ data: JSON.stringify({ type: 'error', message: '失败' }) } as MessageEvent);

    expect(events).toEqual([{ type: 'error', message: '失败' }]);
  });

  it('sends approval and manual input only while open', () => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const ws = asFake(new WebSocket('ws://x', ['geass', 'tok']));

    sendApproval(ws as unknown as WebSocket, 'a-1', true);
    sendManualInput(ws as unknown as WebSocket, {
      action: 'click',
      x: 0.5,
      y: 0.5,
      button: 'left',
    });

    expect(ws.sent.map((raw) => JSON.parse(raw))).toEqual([
      { type: 'approval', id: 'a-1', approved: true },
      { type: 'manual_input', action: 'click', x: 0.5, y: 0.5, button: 'left' },
    ]);

    ws.readyState = 3;
    sendApproval(ws as unknown as WebSocket, 'a-2', false);
    expect(ws.sent).toHaveLength(2);
  });
});
