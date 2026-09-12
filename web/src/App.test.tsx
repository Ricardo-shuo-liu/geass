import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';

const mocks = vi.hoisted(() => ({
  apiInfo: vi.fn(),
  pairDevice: vi.fn(),
  stopAgent: vi.fn(),
  transcribe: vi.fn(),
  getTrust: vi.fn(),
  getPrivacyMasks: vi.fn(),
  updateTrust: vi.fn(),
  detectSensitiveRegions: vi.fn(),
  openScreenSocket: vi.fn(),
  openControlSocket: vi.fn(),
  sendApproval: vi.fn(),
  sendManualInput: vi.fn(),
  sendActionDecision: vi.fn(),
  sendPrivacyMask: vi.fn(),
}));

vi.mock('./api', () => mocks);
vi.mock('./ws', () => mocks);

const TOKEN_KEY = 'geass-token';

let controlHandler: ((event: unknown) => void) | null = null;

function fakeSocket(): WebSocket {
  return {
    readyState: 1,
    close: vi.fn(),
    send: vi.fn(),
    onmessage: null,
    onclose: null,
    onerror: null,
  } as unknown as WebSocket;
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  (window.localStorage as Storage | undefined)?.clear();
  const legacy = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => legacy.get(key) ?? null,
    setItem: (key: string, value: string) => legacy.set(key, String(value)),
    removeItem: (key: string) => legacy.delete(key),
    clear: () => legacy.clear(),
  });
  window.history.replaceState(null, '', '/');
  mocks.apiInfo.mockResolvedValue({ ok: true });
  mocks.pairDevice.mockResolvedValue('paired-token');
  mocks.getTrust.mockResolvedValue({
    mode: 'smart',
    visual_delay_ms: 600,
    overrides: {},
    task_allow_all: false,
  });
  mocks.getPrivacyMasks.mockResolvedValue({ enabled: false, masks: [] });
  mocks.updateTrust.mockResolvedValue({
    mode: 'smart',
    visual_delay_ms: 600,
    overrides: {},
    task_allow_all: false,
  });
  mocks.detectSensitiveRegions.mockResolvedValue({
    regions: [
      { x: 0.1, y: 0.2, w: 0.3, h: 0.1, source: 'password', label: '密码输入框' },
    ],
    sources: { password_fields: 1, keyword_matches: 0 },
    keywords: ['密码'],
  });
  mocks.openScreenSocket.mockImplementation(() => fakeSocket());
  controlHandler = null;
  mocks.openControlSocket.mockImplementation(
    (_token: string, onMessage: (event: unknown) => void) => {
      controlHandler = onMessage;
      return fakeSocket();
    },
  );
  vi.stubGlobal('WebSocket', { OPEN: 1 });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('App pairing', () => {
  it('exchanges a hash pairing code and stores the token in sessionStorage', async () => {
    window.history.replaceState(null, '', '/#pair=abc123');
    render(<App />);

    await waitFor(() => expect(mocks.pairDevice).toHaveBeenCalledWith('abc123'));
    await waitFor(() =>
      expect(sessionStorage.getItem(TOKEN_KEY)).toBe('paired-token'),
    );
    expect(await screen.findByText('资源')).toBeInTheDocument();
    expect(window.location.hash).toBe('');
  });

  it('restores a valid session token without pairing again', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);

    expect(await screen.findByText('资源')).toBeInTheDocument();
    expect(mocks.apiInfo).toHaveBeenCalledWith('stored-token');
    expect(mocks.pairDevice).not.toHaveBeenCalled();
  });

  it('drops a stale session token and falls back to the connect panel', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stale-token');
    mocks.apiInfo.mockRejectedValue(new Error('连接失败（HTTP 401）'));
    render(<App />);

    expect(await screen.findByRole('button', { name: 'CONNECT' })).toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('pairs with a new code even when a stale session token exists', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stale-token');
    mocks.apiInfo.mockRejectedValue(new Error('连接失败（HTTP 401）'));
    window.history.replaceState(null, '', '/#pair=fresh-code');
    render(<App />);

    await waitFor(() => expect(mocks.pairDevice).toHaveBeenCalledWith('fresh-code'));
    await waitFor(() =>
      expect(sessionStorage.getItem(TOKEN_KEY)).toBe('paired-token'),
    );
    expect(await screen.findByText('资源')).toBeInTheDocument();
  });

  it('shows an actionable error when the pairing code is invalid', async () => {
    window.history.replaceState(null, '', '/#pair=expired');
    mocks.pairDevice.mockRejectedValue(new Error('配对码已过期'));
    render(<App />);

    expect(await screen.findByText(/配对码已过期/)).toBeInTheDocument();
    expect(
      screen.getByText('geass serve --qr', { selector: 'code' }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('clears the session token when disconnecting', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');

    fireEvent.click(screen.getByRole('button', { name: '断开' }));

    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(await screen.findByRole('button', { name: 'CONNECT' })).toBeInTheDocument();
  });

  it('loads trust settings and opens the trust panel', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');

    await waitFor(() => expect(mocks.getTrust).toHaveBeenCalledWith('stored-token'));
    fireEvent.click(screen.getByRole('button', { name: '信任' }));

    expect(screen.getByText('信任与隐私')).toBeInTheDocument();
    expect(screen.getByText('动作预览')).toBeInTheDocument();
    expect(screen.getByText('隐私遮罩')).toBeInTheDocument();
  });

  it('shows a confirmation card and sends the decision', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');

    act(() => {
      controlHandler?.({
        type: 'action_proposal',
        id: 'p1',
        tool: 'open_terminal',
        kind: 'command',
        target: { command: 'echo hi' },
        summary: '终端命令：echo hi',
        decision_required: true,
        delay_ms: 0,
        step: 2,
        total_steps: 4,
        undoable: false,
        expires_in: 30,
      });
    });

    expect(await screen.findByText('终端命令：echo hi')).toBeInTheDocument();
    expect(screen.getByText('步骤 2/4')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '执行' }));

    expect(mocks.sendActionDecision).toHaveBeenCalledWith(
      expect.anything(),
      'p1',
      true,
      expect.objectContaining({ command: 'echo hi' }),
    );
  });

  it('shows an auto strip and can intercept', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');

    act(() => {
      controlHandler?.({
        type: 'action_proposal',
        id: 'p2',
        tool: 'click',
        kind: 'point',
        target: { x: 0.4, y: 0.6 },
        summary: '单击 (0.40, 0.60)',
        decision_required: false,
        delay_ms: 800,
        step: 1,
        total_steps: 0,
        undoable: false,
        expires_in: 30,
      });
    });

    expect(await screen.findByTestId('action-strip')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '拦截' }));

    expect(mocks.sendActionDecision).toHaveBeenCalledWith(
      expect.anything(),
      'p2',
      false,
      expect.objectContaining({ x: 0.4, y: 0.6 }),
    );
  });

  it('auto-detects sensitive regions and applies a suggestion', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');
    fireEvent.click(screen.getByRole('button', { name: '信任' }));

    fireEvent.click(screen.getByRole('button', { name: '自动识别敏感区域' }));
    expect(await screen.findByText(/密码框 · 密码输入框/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '应用' }));
    expect(mocks.sendPrivacyMask).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        action: 'add',
        rect: expect.objectContaining({ w: 0.3 }),
      }),
    );
  });

  it('keeps a short afterglow after an auto action', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'stored-token');
    render(<App />);
    await screen.findByText('资源');

    act(() => {
      controlHandler?.({
        type: 'action_proposal',
        id: 'p3',
        tool: 'move',
        kind: 'point',
        target: { x: 0.1, y: 0.1 },
        summary: '移动鼠标到 (0.10, 0.10)',
        decision_required: false,
        delay_ms: 600,
        step: 1,
        total_steps: 0,
        undoable: false,
        expires_in: 30,
      });
    });
    expect(await screen.findByTestId('action-strip')).toBeInTheDocument();

    act(() => {
      controlHandler?.({
        type: 'action_resolved',
        id: 'p3',
        approved: true,
        auto: true,
      });
    });

    expect(await screen.findByText('✓ 已执行')).toBeInTheDocument();
  });
});
