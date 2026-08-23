import { useCallback, useEffect, useRef, useState } from 'react';
import { ApprovalModal } from './components/ApprovalModal';
import { CommandBar } from './components/CommandBar';
import { ConnectPanel } from './components/ConnectPanel';
import { DanmakuPanel } from './components/DanmakuPanel';
import { DanmakuOverlay } from './components/DanmakuOverlay';
import { LogDrawer } from './components/LogDrawer';
import PlanCard from './components/PlanCard';
import { ScreenView } from './components/ScreenView';
import { apiInfo, stopAgent, transcribe } from './api';
import { openControlSocket, openScreenSocket, sendApproval } from './ws';
import type {
  ApprovalRequest,
  ControlEvent,
  DanmakuDensity,
  DanmakuIntensity,
  DanmakuSize,
  TaskPlan,
} from './types';

const TOKEN_KEY = 'geass-token';
const DENSITY_KEY = 'geass-danmaku-density';
const SIZE_KEY = 'geass-danmaku-size';
const INTENSITY_KEY = 'geass-danmaku-intensity';
const EVENT_LIMIT = 200;

const DENSITY_ORDER: DanmakuDensity[] = ['all', 'key', 'minimal'];
const DENSITY_LABELS: Record<DanmakuDensity, string> = {
  all: '全部',
  key: '关键',
  minimal: '少量',
};

const SIZE_ORDER: DanmakuSize[] = ['small', 'medium', 'large'];
const INTENSITY_ORDER: DanmakuIntensity[] = ['light', 'standard', 'strong'];

const BUSY_STATES = [
  'accepted',
  'thinking',
  'planned',
  'acting',
  'acted',
  'awaiting_approval',
  'cancelling',
];

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function initialDensity(): DanmakuDensity {
  const value = localStorage.getItem(DENSITY_KEY);
  return DENSITY_ORDER.includes(value as DanmakuDensity)
    ? (value as DanmakuDensity)
    : 'key';
}

function initialSetting<T extends string>(
  key: string,
  fallback: T,
  valid: readonly T[],
): T {
  const value = localStorage.getItem(key);
  return value && valid.includes(value as T) ? (value as T) : fallback;
}

export default function App() {
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(TOKEN_KEY),
  );
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [frame, setFrame] = useState<Blob | null>(null);
  const [screenOpen, setScreenOpen] = useState(true);
  const [events, setEvents] = useState<ControlEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [density, setDensity] = useState<DanmakuDensity>(initialDensity);
  const [danmakuSize, setDanmakuSize] = useState<DanmakuSize>(() =>
    initialSetting(SIZE_KEY, 'medium', SIZE_ORDER),
  );
  const [danmakuIntensity, setDanmakuIntensity] =
    useState<DanmakuIntensity>(() =>
      initialSetting(INTENSITY_KEY, 'standard', INTENSITY_ORDER),
    );
  const [logOpen, setLogOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingApproval, setPendingApproval] =
    useState<ApprovalRequest | null>(null);
  const [plan, setPlan] = useState<TaskPlan | null>(null);

  const controlRef = useRef<WebSocket | null>(null);
  const voiceRecRef = useRef<unknown>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);

  const addEvent = useCallback((event: ControlEvent) => {
    const stamped: ControlEvent = {
      ...event,
      _time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    };
    setEvents((previous) => [...previous.slice(-(EVENT_LIMIT - 1)), stamped]);
    if (event.type === 'agent_status') {
      setBusy(BUSY_STATES.includes(event.state));
      if (event.state === 'planned' && event.plan) {
        setPlan(event.plan);
      } else if (event.state === 'accepted') {
        setPlan(null);
      }
    } else if (event.type === 'approval_request') {
      setBusy(true);
      setPendingApproval(event);
    } else if (event.type === 'approval_resolved') {
      setPendingApproval((previous) =>
        previous && previous.id === event.id ? null : previous,
      );
    } else if (event.type === 'agent_result') {
      setBusy(false);
      setPlan(null);
    }
  }, []);

  const connect = useCallback(async (value: string) => {
    setConnecting(true);
    setConnectError(null);
    try {
      await apiInfo(value);
      localStorage.setItem(TOKEN_KEY, value);
      setToken(value);
    } catch (error) {
      setConnectError(errorMessage(error));
    } finally {
      setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setFrame(null);
    setEvents([]);
    setBusy(false);
    setPendingApproval(null);
    setPlan(null);
    setLogOpen(false);
    setSettingsOpen(false);
  }, []);

  const sendCommand = useCallback(
    (text: string) => {
      const value = text.trim();
      if (!value) return;
      const ws = controlRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        addEvent({
          type: 'agent_status',
          state: 'error',
          step: 0,
          tool: null,
          message: '控制通道未连接，请稍候重试',
        });
        return;
      }
      ws.send(JSON.stringify({ type: 'command', text: value }));
      addEvent({
        type: 'agent_status',
        state: 'accepted',
        step: 0,
        tool: null,
        message: `发送命令：${value}`,
      });
    },
    [addEvent],
  );

  const stop = useCallback(async () => {
    if (!token) return;
    try {
      await stopAgent(token);
    } catch (error) {
      addEvent({
        type: 'agent_status',
        state: 'error',
        step: 0,
        tool: null,
        message: `停止失败：${errorMessage(error)}`,
      });
    }
  }, [token, addEvent]);

  const respondApproval = useCallback(
    (approved: boolean) => {
      const approval = pendingApproval;
      if (!approval) return;
      const ws = controlRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        sendApproval(ws, approval.id, approved);
      }
      setPendingApproval(null);
    },
    [pendingApproval],
  );

  const changeDensity = useCallback((value: DanmakuDensity) => {
    setDensity(value);
    localStorage.setItem(DENSITY_KEY, value);
  }, []);

  const changeDanmakuSize = useCallback((value: DanmakuSize) => {
    setDanmakuSize(value);
    localStorage.setItem(SIZE_KEY, value);
  }, []);

  const changeDanmakuIntensity = useCallback((value: DanmakuIntensity) => {
    setDanmakuIntensity(value);
    localStorage.setItem(INTENSITY_KEY, value);
  }, []);

  const recordFallback = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (!chunks.length) return;
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        setTranscribing(true);
        try {
          if (!token) throw new Error('未连接');
          const text = await transcribe(token, blob);
          sendCommand(text);
        } catch (error) {
          addEvent({
            type: 'agent_status',
            state: 'error',
            step: 0,
            tool: null,
            message: `语音识别失败：${errorMessage(error)}`,
          });
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecRef.current = recorder;
      recorder.start();
      setListening(true);
      window.setTimeout(() => {
        if (mediaRecRef.current && mediaRecRef.current.state === 'recording') {
          mediaRecRef.current.stop();
        }
      }, 15000);
    } catch (error) {
      addEvent({
        type: 'agent_status',
        state: 'error',
        step: 0,
        tool: null,
        message: `无法使用麦克风：${errorMessage(error)}`,
      });
    }
  }, [token, addEvent, sendCommand]);

  const startVoice = useCallback(() => {
    const w = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike;
      webkitSpeechRecognition?: new () => SpeechRecognitionLike;
    };
    const Recognition = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Recognition) {
      void recordFallback();
      return;
    }
    const recognition = new Recognition();
    recognition.lang = 'zh-CN';
    recognition.interimResults = false;
    recognition.onresult = (event: SpeechResultEvent) => {
      const text = event.results[0]?.[0]?.transcript ?? '';
      if (text) sendCommand(text);
    };
    recognition.onerror = () => {
      setListening(false);
      void recordFallback();
    };
    recognition.onend = () => setListening(false);
    voiceRecRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [recordFallback, sendCommand]);

  const stopVoice = useCallback(() => {
    const recognition = voiceRecRef.current as { stop?: () => void } | null;
    if (recognition) {
      try {
        recognition.stop?.();
      } catch {
        // 忽略停止时的异常
      }
      voiceRecRef.current = null;
    }
    if (mediaRecRef.current && mediaRecRef.current.state === 'recording') {
      mediaRecRef.current.stop();
      mediaRecRef.current = null;
    }
    setListening(false);
  }, []);

  useEffect(() => {
    if (!token) return;
    let disposed = false;
    let reconnectTimer: number | undefined;
    let screenWs: WebSocket | null = null;
    let controlWs: WebSocket | null = null;

    const scheduleReconnect = () => {
      if (!disposed) reconnectTimer = window.setTimeout(connectSockets, 2000);
    };

    const connectSockets = () => {
      if (disposed) return;
      window.clearTimeout(reconnectTimer);
      screenWs?.close();
      controlWs?.close();
      screenWs = openScreenSocket(
        token,
        (blob) => {
          setScreenOpen(true);
          setFrame(blob);
        },
        (event) => {
          if (event.code === 4401) {
            localStorage.removeItem(TOKEN_KEY);
            setToken(null);
            return;
          }
          setScreenOpen(false);
          scheduleReconnect();
        },
        () => {},
      );
      controlWs = openControlSocket(
        token,
        (event) => addEvent(event),
        (event) => {
          if (event.code === 4401) {
            localStorage.removeItem(TOKEN_KEY);
            setToken(null);
            return;
          }
          scheduleReconnect();
        },
      );
      controlRef.current = controlWs;
    };

    connectSockets();
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      screenWs?.close();
      controlWs?.close();
      controlRef.current = null;
    };
  }, [token, addEvent]);

  if (!token) {
    return (
      <ConnectPanel
        connecting={connecting}
        error={connectError}
        onConnect={connect}
      />
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="logo">GEASS</h1>
        <div className="topbar-actions">
          <span className={`chip ${busy ? 'busy' : 'idle'}`}>
            <span className="dot" />
            {busy ? '执行中' : '空闲'}
          </span>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setSettingsOpen((value) => !value)}
            title="弹幕设置"
          >
            弹幕·{DENSITY_LABELS[density]}
          </button>
          <button
            type="button"
            className="tool-btn"
            onClick={() => setLogOpen(true)}
          >
            日志
          </button>
          <button type="button" className="tool-btn danger" onClick={disconnect}>
            断开
          </button>
        </div>
      </header>

      {settingsOpen && (
        <DanmakuPanel
          density={density}
          size={danmakuSize}
          intensity={danmakuIntensity}
          onChangeDensity={changeDensity}
          onChangeSize={changeDanmakuSize}
          onChangeIntensity={changeDanmakuIntensity}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      <main className="stage">
        <ScreenView frame={frame} />
        <DanmakuOverlay
          events={events}
          density={density}
          size={danmakuSize}
          intensity={danmakuIntensity}
        />
        {!screenOpen && (
          <div className="screen-closed">屏幕连接已断开，正在重连…</div>
        )}
        {pendingApproval && (
          <ApprovalModal
            approval={pendingApproval}
            onApprove={() => respondApproval(true)}
            onDeny={() => respondApproval(false)}
          />
        )}
        {plan && <PlanCard plan={plan} onClose={() => setPlan(null)} />}
      </main>

      <footer className="dock">
        <CommandBar
          busy={busy}
          listening={listening}
          transcribing={transcribing}
          onSend={sendCommand}
          onStop={() => void stop()}
          onStartVoice={startVoice}
          onStopVoice={stopVoice}
        />
      </footer>

      <LogDrawer
        open={logOpen}
        busy={busy}
        events={events}
        onClose={() => setLogOpen(false)}
      />
    </div>
  );
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

interface SpeechResultEvent {
  results: Array<Array<{ transcript: string }>>;
}
