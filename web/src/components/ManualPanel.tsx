import { useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { ManualAction } from '../types';

interface Props {
  onAction: (action: ManualAction) => void;
  onClose: () => void;
}

const CHARACTER_ROWS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm'],
];

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function ManualPanel({ onAction, onClose }: Props) {
  const [mouseHeight, setMouseHeight] = useState(130);
  const [panelHeight, setPanelHeight] = useState(310);
  const [collapsed, setCollapsed] = useState({
    mouse: false,
    keyboard: false,
  });
  const dividerRef = useRef<{ y: number; height: number } | null>(null);
  const panelDragRef = useRef<{ y: number; height: number } | null>(null);

  const onDividerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dividerRef.current = { y: event.clientY, height: mouseHeight };
  };

  const onDividerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const divider = dividerRef.current;
    if (!divider) return;
    const next = divider.height - (event.clientY - divider.y);
    setMouseHeight(Math.min(300, Math.max(92, Math.round(next))));
  };

  const onDividerUp = () => {
    dividerRef.current = null;
  };

  const onPanelResizeDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    panelDragRef.current = { y: event.clientY, height: panelHeight };
  };

  const onPanelResizeMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = panelDragRef.current;
    if (!drag) return;
    const maxHeight = Math.min(560, Math.round(window.innerHeight * 0.72));
    setPanelHeight(
      Math.min(maxHeight, Math.max(180, drag.height - (event.clientY - drag.y))),
    );
  };

  const onPanelResizeUp = () => {
    panelDragRef.current = null;
  };

  const toggleAll = () => {
    setCollapsed((previous) => {
      const bothCollapsed = previous.mouse && previous.keyboard;
      return {
        mouse: !bothCollapsed,
        keyboard: !bothCollapsed,
      };
    });
  };

  return (
    <div className="manual-panel" style={{ height: `${panelHeight}px` }}>
      <div
        className="manual-resize"
        onPointerDown={onPanelResizeDown}
        onPointerMove={onPanelResizeMove}
        onPointerUp={onPanelResizeUp}
        onPointerCancel={onPanelResizeUp}
        title="拖动顶部调整面板高度"
      >
        <span>⋮⋮⋮</span>
      </div>
      <div className="manual-panel-head">
        <span className="manual-hint">直控 · 同屏键鼠</span>
        <button
          type="button"
          className="manual-toggle"
          onClick={toggleAll}
        >
          {collapsed.mouse && collapsed.keyboard ? '展开' : '折叠'}
        </button>
        <button
          type="button"
          className="manual-close"
          onClick={onClose}
          aria-label="关闭直控"
        >
          ✕
        </button>
      </div>
      <div className="manual-body">
        <section className="manual-section">
          <div className="manual-section-head">
            <span>🖱 鼠标</span>
            <button
              type="button"
              onClick={() =>
                setCollapsed((previous) => ({
                  ...previous,
                  mouse: !previous.mouse,
                }))
              }
              aria-label="折叠鼠标区"
            >
              {collapsed.mouse ? '+' : '−'}
            </button>
          </div>
          {!collapsed.mouse && (
            <div className="manual-mouse" style={{ height: `${mouseHeight}px` }}>
              <Touchpad onAction={onAction} />
            </div>
          )}
        </section>
        {!collapsed.mouse && !collapsed.keyboard && (
          <div
            className="manual-divider"
            onPointerDown={onDividerDown}
            onPointerMove={onDividerMove}
            onPointerUp={onDividerUp}
            onPointerCancel={onDividerUp}
            title="拖动调整鼠标区大小"
          />
        )}
        <section className="manual-section">
          <div className="manual-section-head">
            <span>⌨️ 键盘</span>
            <button
              type="button"
              onClick={() =>
                setCollapsed((previous) => ({
                  ...previous,
                  keyboard: !previous.keyboard,
                }))
              }
              aria-label="折叠键盘区"
            >
              {collapsed.keyboard ? '+' : '−'}
            </button>
          </div>
          {!collapsed.keyboard && (
            <div className="manual-keyboard">
              <VirtualKeyboard onAction={onAction} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

const TOUCHPAD_SENSITIVITY = 1.8;
const MOVE_THROTTLE_MS = 20;
const MOVE_THRESHOLD = 0.0008;

function Touchpad({ onAction }: { onAction: Props['onAction'] }) {
  const padRef = useRef<HTMLDivElement | null>(null);
  const cursorRef = useRef({ x: 0.5, y: 0.5 });
  const [dot, setDot] = useState<{ x: number; y: number } | null>(null);
  const gestureRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    moved: boolean;
    lastSent: number;
    timer: number | null;
    longPressed: boolean;
    dragStartX: number;
    dragStartY: number;
  } | null>(null);
  const tapRef = useRef<{ time: number; x: number; y: number } | null>(null);

  const padPoint = (event: ReactPointerEvent<HTMLDivElement>) => {
    const pad = padRef.current;
    if (!pad) return null;
    const rect = pad.getBoundingClientRect();
    return {
      x: clamp01((event.clientX - rect.left) / rect.width),
      y: clamp01((event.clientY - rect.top) / rect.height),
    };
  };

  const sendMove = (position: { x: number; y: number }) => {
    cursorRef.current = position;
    setDot(position);
    onAction({ action: 'move', x: position.x, y: position.y });
  };

  const down = (event: ReactPointerEvent<HTMLDivElement>) => {
    const position = padPoint(event);
    if (!position) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDot(cursorRef.current);
    const timer = window.setTimeout(() => {
      if (gestureRef.current && !gestureRef.current.moved) {
        gestureRef.current.longPressed = true;
        onAction({
          action: 'right_click',
          x: cursorRef.current.x,
          y: cursorRef.current.y,
        });
      }
    }, 550);
    gestureRef.current = {
      pointerId: event.pointerId,
      startX: position.x,
      startY: position.y,
      lastX: position.x,
      lastY: position.y,
      moved: false,
      lastSent: performance.now(),
      timer,
      longPressed: false,
      dragStartX: cursorRef.current.x,
      dragStartY: cursorRef.current.y,
    };
  };

  const drag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const position = padPoint(event);
    if (!position) return;
    const deltaX = (position.x - gesture.lastX) * TOUCHPAD_SENSITIVITY;
    const deltaY = (position.y - gesture.lastY) * TOUCHPAD_SENSITIVITY;
    gesture.lastX = position.x;
    gesture.lastY = position.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > MOVE_THRESHOLD) {
      gesture.moved = true;
    }
    const cursor = {
      x: clamp01(cursorRef.current.x + deltaX),
      y: clamp01(cursorRef.current.y + deltaY),
    };
    const now = performance.now();
    if (now - gesture.lastSent >= MOVE_THROTTLE_MS) {
      gesture.lastSent = now;
      sendMove(cursor);
    } else {
      cursorRef.current = cursor;
      setDot(cursor);
    }
  };

  const up = (event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if (gesture.timer !== null) window.clearTimeout(gesture.timer);
    const position = padPoint(event);
    gestureRef.current = null;
    if (gesture.longPressed) return;

    if (gesture.moved) {
      onAction({
        action: 'drag',
        x1: gesture.dragStartX,
        y1: gesture.dragStartY,
        x2: cursorRef.current.x,
        y2: cursorRef.current.y,
      });
      tapRef.current = null;
      return;
    }

    const now = performance.now();
    const previous = tapRef.current;
    if (
      previous &&
      position &&
      now - previous.time < 320 &&
      Math.hypot(previous.x - position.x, previous.y - position.y) < 0.05
    ) {
      onAction({
        action: 'double_click',
        x: cursorRef.current.x,
        y: cursorRef.current.y,
      });
      tapRef.current = null;
    } else {
      onAction({
        action: 'click',
        x: cursorRef.current.x,
        y: cursorRef.current.y,
      });
      if (position) {
        tapRef.current = { time: now, x: position.x, y: position.y };
      }
    }
  };

  const buttonAction = (
    action: 'click' | 'double_click' | 'right_click',
  ) => {
    const position = dot ?? cursorRef.current;
    onAction({ action, x: position.x, y: position.y });
  };

  return (
    <>
      <div
        ref={padRef}
        className="touchpad"
        onPointerDown={down}
        onPointerMove={drag}
        onPointerUp={up}
        onPointerCancel={() => {
          const gesture = gestureRef.current;
          if (gesture?.timer) window.clearTimeout(gesture.timer);
          gestureRef.current = null;
        }}
      >
        {dot && (
          <span
            className="touchpad-dot"
            style={{ left: `${dot.x * 100}%`, top: `${dot.y * 100}%` }}
          />
        )}
      </div>
      <div className="mouse-buttons">
        <button type="button" onClick={() => buttonAction('click')}>
          左键
        </button>
        <button type="button" onClick={() => buttonAction('double_click')}>
          双击
        </button>
        <button type="button" onClick={() => buttonAction('right_click')}>
          右键
        </button>
        <button
          type="button"
          onClick={() => onAction({ action: 'scroll', dx: 0, dy: 2 })}
        >
          ▲ 滚
        </button>
        <button
          type="button"
          onClick={() => onAction({ action: 'scroll', dx: 0, dy: -2 })}
        >
          ▼ 滚
        </button>
      </div>
    </>
  );
}

function VirtualKeyboard({ onAction }: { onAction: Props['onAction'] }) {
  const [mods, setMods] = useState({
    shift: false,
    ctrl: false,
    alt: false,
    super: false,
  });

  const toggle = (name: 'shift' | 'ctrl' | 'alt' | 'super') => {
    setMods((previous) => ({ ...previous, [name]: !previous[name] }));
  };

  const clearMods = () =>
    setMods({ shift: false, ctrl: false, alt: false, super: false });

  const pressCharacter = (label: string) => {
    const combo = [
      mods.shift ? 'shift' : '',
      mods.ctrl ? 'ctrl' : '',
      mods.alt ? 'alt' : '',
      mods.super ? 'super' : '',
      label,
    ].filter(Boolean);
    if (combo.length > 1) {
      onAction({ action: 'key', combo: combo.join('+') });
    } else {
      onAction({ action: 'type', text: label });
    }
    clearMods();
  };

  const pressKey = (combo: string) => {
    onAction({ action: 'key', combo });
    clearMods();
  };

  return (
    <div className="virtual-keyboard">
      {CHARACTER_ROWS.map((row, rowIndex) => (
        <div className="vk-row" key={`row-${rowIndex}`}>
          {row.map((label) => (
            <button
              type="button"
              key={label}
              onPointerDown={(event) => {
                event.preventDefault();
                pressCharacter(label);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      ))}
      <div className="vk-row">
        <button
          type="button"
          className={`vk-mod ${mods.shift ? 'active' : ''}`}
          onClick={() => toggle('shift')}
        >
          ⇧
        </button>
        <button
          type="button"
          className={`vk-mod ${mods.ctrl ? 'active' : ''}`}
          onClick={() => toggle('ctrl')}
        >
          Ctrl
        </button>
        <button
          type="button"
          className={`vk-mod ${mods.super ? 'active' : ''}`}
          onClick={() => toggle('super')}
        >
          Win
        </button>
        <button
          type="button"
          className={`vk-mod ${mods.alt ? 'active' : ''}`}
          onClick={() => toggle('alt')}
        >
          Alt
        </button>
        <button
          type="button"
          className="vk-wide"
          onClick={() => pressKey('backspace')}
        >
          ⌫
        </button>
      </div>
      <div className="vk-row">
        <button type="button" onClick={() => pressKey('tab')}>
          Tab
        </button>
        <button type="button" onClick={() => pressKey('escape')}>
          Esc
        </button>
        <button type="button" onClick={() => pressKey('left')}>
          ◀
        </button>
        <button type="button" onClick={() => pressKey('up')}>
          ▲
        </button>
        <button type="button" onClick={() => pressKey('down')}>
          ▼
        </button>
        <button type="button" onClick={() => pressKey('right')}>
          ▶
        </button>
        <button
          type="button"
          className="vk-wide"
          onClick={() => onAction({ action: 'type', text: ' ' })}
        >
          ␣
        </button>
        <button
          type="button"
          className="vk-wide"
          onClick={() => pressKey('enter')}
        >
          ↵
        </button>
      </div>
    </div>
  );
}
