import { useCallback, useEffect, useRef, useState } from 'react';
import { ApprovalModal } from './components/ApprovalModal';
import { ActionPreviewCard, ActionPreviewStrip } from './components/ActionPreviewCard';
import { CommandBar } from './components/CommandBar';
import { ConnectPanel } from './components/ConnectPanel';
import { DanmakuPanel } from './components/DanmakuPanel';
import { DanmakuOverlay } from './components/DanmakuOverlay';
import { GestureLayer } from './components/GestureLayer';
import { LogDrawer } from './components/LogDrawer';
import { ManualPanel } from './components/ManualPanel';
import PlanCard from './components/PlanCard';
import { ResourcePanel } from './components/ResourcePanel';
import { ScreenView } from './components/ScreenView';
import { TrustPanel } from './components/TrustPanel';
import {
  apiInfo,
  detectSensitiveRegions,
  getPrivacyMasks,
  getTrust,
  pairDevice,
  stopAgent,
  transcribe,
  updateTrust,
} from './api';
import { clearPairCode, readPairCode } from './pairing';
import {
  clearLegacyToken,
  clearSessionToken,
  readSessionToken,
  writeSessionToken,
} from './storage';
import {
  openControlSocket,
  openScreenSocket,
  sendActionDecision,
  sendPrivacyMask,
  sendApproval,
  sendManualInput,
} from './ws';
import type {
  ActionProposal,
  ApprovalRequest,
  ControlEvent,
  DanmakuDensity,
  DanmakuIntensity,
  DanmakuSize,
  ManualAction,
  PrivacyMask,
  SensitiveRegion,
  TaskPlan,
  TrustSettings,
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
  'awaiting_action',
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
  const [token, setToken] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [booting, setBooting] = useState(true);
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
  const [manualOpen, setManualOpen] = useState(false);
  const [resourcesOpen, setResourcesOpen] = useState(false);
  const [trustOpen, setTrustOpen] = useState(false);
  const [trust, setTrust] = useState<TrustSettings>({
    mode: 'smart',
    visual_delay_ms: 600,
    overrides: {},
    task_allow_all: false,
  });
  const [masks, setMasks] = useState<PrivacyMask[]>([]);
  const [masksEnabled, setMasksEnabled] = useState(false);
  const [maskMode, setMaskMode] = useState(false);
  const [pendingAction, setPendingAction] = useState<ActionProposal | null>(null);
  const [previewTarget, setPreviewTarget] = useState<Record<string, unknown>>({});
  const [previewResolved, setPreviewResolved] = useState<{
    approved: boolean;
    auto: boolean;
  } | null>(null);
  const [suggestions, setSuggestions] = useState<SensitiveRegion[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [detectNote, setDetectNote] = useState<string | null>(null);

  // 扫码/恢复会话：优先使用 sessionStorage 中的 Token，其次消费 URL 中的一次性配对码。
  useEffect(() => {
    clearLegacyToken(TOKEN_KEY);
    let disposed = false;
    const bootstrap = async () => {
      const stored = readSessionToken(TOKEN_KEY);
      if (stored) {
        let valid = false;
        try {
          await apiInfo(stored);
          valid = true;
        } catch {
          clearSessionToken(TOKEN_KEY);
        }
        if (valid) {
          if (!disposed) {
            setToken(stored);
            clearPairCode();
            setBooting(false);
          }
          return;
        }
      }
      const code = readPairCode(window.location.hash);
      if (!code) {
        if (!disposed) {
          if (stored) setConnectError('会话已失效，请重新扫码或输入 Token');
          setBooting(false);
        }
        return;
      }
      try {
        const value = await pairDevice(code);
        writeSessionToken(TOKEN_KEY, value);
        clearPairCode();
        if (!disposed) {
          setConnectError(null);
          setToken(value);
        }
      } catch (error) {
        clearPairCode();
        if (!disposed) {
          setConnectError(
            `${errorMessage(error)}；请在电脑上重新运行 geass serve --qr，或手动输入 Token`,
          );
        }
      } finally {
        if (!disposed) setBooting(false);
      }
    };
    void bootstrap();
    return () => {
      disposed = true;
    };
  }, []);

  const controlRef = useRef<WebSocket | null>(null);
  const previewClearRef = useRef<number | null>(null);
  const pendingActionRef = useRef<ActionProposal | null>(null);

  useEffect(() => {
    pendingActionRef.current = pendingAction;
  }, [pendingAction]);
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
    } else if (event.type === 'action_proposal') {
      if (previewClearRef.current !== null) {
        window.clearTimeout(previewClearRef.current);
        previewClearRef.current = null;
      }
      setPreviewResolved(null);
      setPendingAction(event);
      setPreviewTarget({ ...event.target });
      if (event.decision_required) setBusy(true);
    } else if (event.type === 'action_resolved') {
      const current = pendingActionRef.current;
      if (current && current.id === event.id) {
        setPreviewResolved({ approved: event.approved, auto: event.auto });
        if (previewClearRef.current !== null) {
          window.clearTimeout(previewClearRef.current);
        }
        previewClearRef.current = window.setTimeout(() => {
          previewClearRef.current = null;
          setPendingAction(null);
          setPreviewResolved(null);
        }, 1200);
      }
    } else if (event.type === 'privacy_masks_changed') {
      setMasks(event.masks);
      setMasksEnabled(event.enabled);
    } else if (event.type === 'trust_changed') {
      setTrust({
        mode: event.mode,
        visual_delay_ms: event.visual_delay_ms,
        overrides: event.overrides,
        task_allow_all: event.task_allow_all,
      });
    }
  }, []);

  const connect = useCallback(async (value: string) => {
    setConnecting(true);
    setConnectError(null);
    try {
      await apiInfo(value);
      writeSessionToken(TOKEN_KEY, value);
      setToken(value);
    } catch (error) {
      clearSessionToken(TOKEN_KEY);
      setConnectError(errorMessage(error));
    } finally {
      setConnecting(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    clearLegacyToken(TOKEN_KEY);
    clearSessionToken(TOKEN_KEY);
    setToken(null);
    setFrame(null);
    setEvents([]);
    setBusy(false);
    setPendingApproval(null);
    setPlan(null);
    setManualOpen(false);
    setResourcesOpen(false);
    setTrustOpen(false);
    setMaskMode(false);
    setPendingAction(null);
    setSuggestions([]);
    setDetectNote(null);
    setLogOpen(false);
    setSettingsOpen(false);
  }, []);

  useEffect(() => {
    if (!token) return;
    let disposed = false;
    void (async () => {
      try {
        const [settings, maskSnapshot] = await Promise.all([
          getTrust(token),
          getPrivacyMasks(token),
        ]);
        if (!disposed) {
          setTrust(settings);
          setMasks(maskSnapshot.masks);
          setMasksEnabled(maskSnapshot.enabled);
        }
      } catch {
        // 保底等待 WS 推送的快照
      }
    })();
    return () => {
      disposed = true;
    };
  }, [token]);

  const updateTrustSettings = useCallback(
    (patch: {
      mode?: TrustSettings['mode'];
      visual_delay_ms?: number;
      overrides?: Record<string, 'auto' | 'confirm' | null>;
      task_allow_all?: boolean;
    }) => {
      if (!token) return;
      void updateTrust(token, patch).then((settings) => {
        setTrust(settings);
      });
    },
    [token],
  );

  const decideAction = useCallback(
    (approved: boolean, target?: Record<string, unknown>) => {
      const ws = controlRef.current;
      if (!ws || !pendingAction) return;
      sendActionDecision(ws, pendingAction.id, approved, target ?? previewTarget);
      if (!approved) setPendingAction(null);
    },
    [pendingAction, previewTarget],
  );

  const emitPrivacyMask = useCallback(
    (
      payload:
        | { action: 'add'; rect: { x: number; y: number; w: number; h: number } }
        | { action: 'remove'; id: string }
        | { action: 'clear' }
        | { action: 'enable' | 'disable' | 'toggle' },
    ) => {
      const ws = controlRef.current;
      if (!ws) return;
      sendPrivacyMask(ws, payload);
    },
    [],
  );

  useEffect(() => {
    if (!maskMode) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMaskMode(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [maskMode]);

  const runDetectSensitive = useCallback(() => {
    if (!token || detecting) return;
    setDetecting(true);
    setDetectNote(null);
    void detectSensitiveRegions(token)
      .then((result) => {
        setSuggestions(result.regions);
        setDetectNote(
          result.regions.length > 0
            ? `识别到 ${result.regions.length} 个建议区域`
            : '未识别到敏感区域，可手动框选',
        );
      })
      .catch(() => {
        setSuggestions([]);
        setDetectNote('自动识别失败，请检查 OCR / AT-SPI 环境');
      })
      .finally(() => setDetecting(false));
  }, [token, detecting]);

  const applySuggestion = useCallback(
    (index: number) => {
      const region = suggestions[index];
      if (!region) return;
      emitPrivacyMask({
        action: 'add',
        rect: { x: region.x, y: region.y, w: region.w, h: region.h },
      });
      setSuggestions((previous) => previous.filter((_item, i) => i !== index));
    },
    [suggestions, emitPrivacyMask],
  );

  const applyAllSuggestions = useCallback(() => {
    for (const region of suggestions) {
      emitPrivacyMask({
        action: 'add',
        rect: { x: region.x, y: region.y, w: region.w, h: region.h },
      });
    }
    setSuggestions([]);
  }, [suggestions, emitPrivacyMask]);

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

  const sendManual = useCallback((action: ManualAction) => {
    const ws = controlRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    sendManualInput(ws, action);
  }, []);

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
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      setListening(false);
      addEvent({
        type: 'agent_status',
        state: 'error',
        step: 0,
        tool: null,
        message: '当前浏览器不支持录音（局域网 HTTP 下需改用文字输入或 HTTPS）',
      });
      return;
    }
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
            clearLegacyToken(TOKEN_KEY);
            clearSessionToken(TOKEN_KEY);
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
            clearLegacyToken(TOKEN_KEY);
            clearSessionToken(TOKEN_KEY);
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
        connecting={connecting || booting}
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
            className={`tool-btn ${manualOpen ? 'active' : ''}`}
            onClick={() => setManualOpen((value) => !value)}
            title="手动直控"
          >
            直控
          </button>
          <button
            type="button"
            className={`tool-btn ${resourcesOpen ? 'active' : ''}`}
            onClick={() => setResourcesOpen((value) => !value)}
            title="资源管理"
          >
            资源
          </button>
          <button
            type="button"
            className={`tool-btn ${trustOpen ? 'active' : ''}`}
            onClick={() => setTrustOpen((value) => !value)}
            title="动作预览与隐私遮罩设置"
          >
            信任
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
        <ScreenView
          frame={frame}
          interactive={manualOpen}
          onManualAction={sendManual}
          masks={masks}
          masksEnabled={masksEnabled}
          maskMode={maskMode}
          onMaskCreate={(rect) => {
            emitPrivacyMask({ action: 'add', rect });
            setMaskMode(false);
          }}
          preview={
            pendingAction
              ? {
                  kind: pendingAction.kind,
                  target: previewTarget,
                  summary: pendingAction.summary,
                }
              : null
          }
          onPreviewTargetChange={
            pendingAction?.kind === 'point' || pendingAction?.kind === 'drag'
              ? setPreviewTarget
              : undefined
          }
        />
        {!manualOpen && (
          <GestureLayer
            onDoubleTap={() => setManualOpen(true)}
            onSwipeUp={() => setLogOpen(true)}
          />
        )}
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
        {pendingAction && !pendingAction.decision_required && (
          <ActionPreviewStrip
            proposal={pendingAction}
            onIntercept={() => decideAction(false)}
            resolved={previewResolved}
          />
        )}
        {pendingAction && pendingAction.decision_required && (
          <ActionPreviewCard
            proposal={pendingAction}
            target={previewTarget}
            resolved={previewResolved}
            onTargetChange={setPreviewTarget}
            onApprove={() => decideAction(true, previewTarget)}
            onDeny={() => decideAction(false)}
            onAllowToolAlways={() => {
              updateTrustSettings({
                overrides: { [pendingAction.tool]: 'auto' },
              });
              decideAction(true, previewTarget);
            }}
            onAllowTask={() => {
              updateTrustSettings({ task_allow_all: true });
              decideAction(true, previewTarget);
            }}
          />
        )}
        {trustOpen && (
          <TrustPanel
            settings={trust}
            masks={masks}
            masksEnabled={masksEnabled}
            maskMode={maskMode}
            suggestions={suggestions}
            detecting={detecting}
            detectNote={detectNote}
            onUpdate={updateTrustSettings}
            onToggleMaskMode={() => setMaskMode((value) => !value)}
            onToggleMasks={(enabled) =>
              emitPrivacyMask({ action: enabled ? 'enable' : 'disable' })
            }
            onDeleteMask={(id) => emitPrivacyMask({ action: 'remove', id })}
            onClearMasks={() => emitPrivacyMask({ action: 'clear' })}
            onDetect={runDetectSensitive}
            onApplySuggestion={applySuggestion}
            onApplyAllSuggestions={applyAllSuggestions}
            onDismissSuggestions={() => {
              setSuggestions([]);
              setDetectNote(null);
            }}
            onClose={() => {
              setTrustOpen(false);
              setMaskMode(false);
            }}
          />
        )}
        {manualOpen && (
          <ManualPanel
            onAction={sendManual}
            onClose={() => setManualOpen(false)}
          />
        )}
        {resourcesOpen && token && (
          <ResourcePanel
            token={token}
            onClose={() => setResourcesOpen(false)}
          />
        )}
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
