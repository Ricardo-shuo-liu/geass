import { useCallback, useEffect, useRef, useState } from 'react';
import { CommandBar } from './components/CommandBar';
import { ConnectPanel } from './components/ConnectPanel';
import { ScreenView } from './components/ScreenView';
import { StatusPanel } from './components/StatusPanel';
import { apiInfo, stopAgent, transcribe } from './api';
import { openControlSocket, openScreenSocket } from './ws';
import type { ControlEvent } from './types';

const TOKEN_KEY = 'geass-token';

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [frame, setFrame] = useState<Blob | null>(null);
  const [screenOpen, setScreenOpen] = useState(true);
  const [events, setEvents] = useState<ControlEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const controlRef = useRef<WebSocket | null>(null);
  const voiceRecRef = useRef<unknown>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);

  const addEvent = useCallback((event: ControlEvent) => {
    setEvents((previous) => [...previous.slice(-59), event]);
    if (event.type === 'agent_status') {
      setBusy(
        ['accepted', 'thinking', 'acting', 'acted', 'cancelling'].includes(
          event.state,
        ),
      );
    } else {
      setBusy(false);
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
        () => {
          setScreenOpen(false);
          scheduleReconnect();
        },
        () => {},
      );
      controlWs = openControlSocket(
        token,
        (event) => addEvent(event),
        scheduleReconnect,
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
    return <ConnectPanel connecting={connecting} error={connectError} onConnect={connect} />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Geass</h1>
        <button type="button" onClick={disconnect}>
          断开
        </button>
      </header>
      <div className="screen-wrap">
        <ScreenView frame={frame} />
        {!screenOpen && <div className="screen-closed">屏幕连接已断开，正在重连…</div>}
      </div>
      <StatusPanel events={events} busy={busy} />
      <CommandBar
        busy={busy}
        listening={listening}
        transcribing={transcribing}
        onSend={sendCommand}
        onStop={() => void stop()}
        onStartVoice={startVoice}
        onStopVoice={stopVoice}
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
