import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from 'react';
import type { ActionKind, ManualAction, PrivacyMask } from '../types';

const MOVE_THROTTLE_MS = 20;
const TAP_DISTANCE = 0.012;
const MOVE_THRESHOLD = 0.0008;

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** 计算 object-fit: contain 后画面在容器里的实际渲染区域。 */
export function contentRect(
  box: { width: number; height: number },
  canvasWidth: number,
  canvasHeight: number,
): Rect | null {
  if (!box.width || !box.height || !canvasWidth || !canvasHeight) return null;
  const scale = Math.min(box.width / canvasWidth, box.height / canvasHeight);
  const width = canvasWidth * scale;
  const height = canvasHeight * scale;
  return {
    left: (box.width - width) / 2,
    top: (box.height - height) / 2,
    width,
    height,
  };
}

/** 由两个归一化点生成规范化矩形（左上角 + 宽高）。 */
export function rectFromPoints(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): { x: number; y: number; w: number; h: number } {
  const x = Math.min(x1, x2);
  const y = Math.min(y1, y2);
  return {
    x: clamp01(x),
    y: clamp01(y),
    w: clamp01(Math.abs(x2 - x1)),
    h: clamp01(Math.abs(y2 - y1)),
  };
}

export interface PreviewView {
  kind: ActionKind;
  target: Record<string, unknown>;
  summary?: string;
}

function pointFromEvent(
  canvas: HTMLCanvasElement,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height || !canvas.width || !canvas.height) {
    return null;
  }
  const scale = Math.min(
    rect.width / canvas.width,
    rect.height / canvas.height,
  );
  const renderedWidth = canvas.width * scale;
  const renderedHeight = canvas.height * scale;
  const offsetX = (rect.width - renderedWidth) / 2;
  const offsetY = (rect.height - renderedHeight) / 2;
  return {
    x: clamp01((clientX - rect.left - offsetX) / renderedWidth),
    y: clamp01((clientY - rect.top - offsetY) / renderedHeight),
  };
}

export function ScreenView({
  frame,
  interactive = false,
  onManualAction,
  masks = [],
  masksEnabled = false,
  maskMode = false,
  onMaskCreate,
  preview = null,
  onPreviewTargetChange,
}: {
  frame: Blob | null;
  interactive?: boolean;
  onManualAction?: (action: ManualAction) => void;
  masks?: PrivacyMask[];
  masksEnabled?: boolean;
  maskMode?: boolean;
  onMaskCreate?: (rect: { x: number; y: number; w: number; h: number }) => void;
  preview?: PreviewView | null;
  onPreviewTargetChange?: (target: Record<string, unknown>) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameBoxRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef<Blob | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [overlayRect, setOverlayRect] = useState<Rect | null>(null);
  const [draft, setDraft] = useState<{ x: number; y: number; w: number; h: number } | null>(
    null,
  );
  const draftRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const drawStartRef = useRef<{ x: number; y: number } | null>(null);
  const previewDragRef = useRef<'point' | 'start' | 'end' | null>(null);
  const gestureRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    moved: boolean;
    lastSent: number;
  } | null>(null);
  const tapRef = useRef<{ time: number; x: number; y: number } | null>(null);
  frameRef.current = frame;

  useEffect(() => {
    let disposed = false;
    let bitmap: ImageBitmap | null = null;

    async function draw() {
      const canvas = canvasRef.current;
      const blob = frameRef.current;
      if (!canvas || !blob) return;
      bitmap = await createImageBitmap(blob);
      if (disposed) {
        bitmap.close();
        return;
      }
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.drawImage(bitmap, 0, 0);
      setCanvasSize({ width: bitmap.width, height: bitmap.height });
      bitmap.close();
      bitmap = null;
    }

    draw().catch(() => {});
    return () => {
      disposed = true;
      if (bitmap) bitmap.close();
    };
  }, [frame]);

  const measure = useCallback(() => {
    const box = frameBoxRef.current;
    if (!box || !canvasSize.width || !canvasSize.height) {
      setOverlayRect(null);
      return;
    }
    const rect = box.getBoundingClientRect();
    setOverlayRect(contentRect({ width: rect.width, height: rect.height }, canvasSize.width, canvasSize.height));
  }, [canvasSize]);

  useEffect(() => {
    measure();
    window.addEventListener('resize', measure);
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    if (observer && frameBoxRef.current) observer.observe(frameBoxRef.current);
    return () => {
      window.removeEventListener('resize', measure);
      observer?.disconnect();
    };
  }, [measure, frame]);

  const normalizedFromEvent = (
    event: ReactPointerEvent<HTMLDivElement>,
  ): { x: number; y: number } | null => {
    const overlay = overlayRef.current;
    if (!overlay) return null;
    const rect = overlay.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return {
      x: clamp01((event.clientX - rect.left) / rect.width),
      y: clamp01((event.clientY - rect.top) / rect.height),
    };
  };

  const onOverlayPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!maskMode) return;
    const point = normalizedFromEvent(event);
    if (!point) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    drawStartRef.current = point;
    const rect = rectFromPoints(point.x, point.y, point.x, point.y);
    draftRef.current = rect;
    setDraft(rect);
  };

  const onOverlayPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (drawStartRef.current) {
      const point = normalizedFromEvent(event);
      if (!point) return;
      const rect = rectFromPoints(
        drawStartRef.current.x,
        drawStartRef.current.y,
        point.x,
        point.y,
      );
      draftRef.current = rect;
      setDraft(rect);
      return;
    }
    const handle = previewDragRef.current;
    if (!handle || !preview || !onPreviewTargetChange) return;
    const point = normalizedFromEvent(event);
    if (!point) return;
    if (handle === 'point') {
      onPreviewTargetChange({
        ...preview.target,
        x: point.x,
        y: point.y,
      });
    } else if (handle === 'start') {
      onPreviewTargetChange({
        ...preview.target,
        x1: point.x,
        y1: point.y,
      });
    } else {
      onPreviewTargetChange({
        ...preview.target,
        x2: point.x,
        y2: point.y,
      });
    }
  };

  const onOverlayPointerUp = () => {
    const currentDraft = draftRef.current;
    if (drawStartRef.current && currentDraft) {
      drawStartRef.current = null;
      draftRef.current = null;
      setDraft(null);
      if (currentDraft.w >= 0.01 && currentDraft.h >= 0.01) onMaskCreate?.(currentDraft);
    }
    previewDragRef.current = null;
  };

  const startPreviewDrag = (
    event: ReactPointerEvent<Element>,
    handle: 'point' | 'start' | 'end',
  ) => {
    if (!onPreviewTargetChange) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    previewDragRef.current = handle;
  };

  const emit = (action: ManualAction) => {
    if (interactive) onManualAction?.(action);
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!interactive || !canvasRef.current) return;
    const point = pointFromEvent(
      canvasRef.current,
      event.clientX,
      event.clientY,
    );
    if (!point) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    gestureRef.current = {
      pointerId: event.pointerId,
      startX: point.x,
      startY: point.y,
      lastX: point.x,
      lastY: point.y,
      moved: false,
      lastSent: performance.now(),
    };
    emit({ action: 'move', x: point.x, y: point.y });
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const gesture = gestureRef.current;
    if (!interactive || !gesture || !canvasRef.current) return;
    if (gesture.pointerId !== event.pointerId) return;
    const point = pointFromEvent(
      canvasRef.current,
      event.clientX,
      event.clientY,
    );
    if (!point) return;
    const previousX = gesture.lastX;
    const previousY = gesture.lastY;
    gesture.lastX = point.x;
    gesture.lastY = point.y;
    const distance = Math.hypot(
      point.x - gesture.startX,
      point.y - gesture.startY,
    );
    if (distance > TAP_DISTANCE) gesture.moved = true;
    const now = performance.now();
    if (
      now - gesture.lastSent >= MOVE_THROTTLE_MS &&
      Math.hypot(
        point.x - previousX,
        point.y - previousY,
      ) > MOVE_THRESHOLD
    ) {
      gesture.lastSent = now;
      emit({ action: 'move', x: point.x, y: point.y });
    }
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const gesture = gestureRef.current;
    if (!interactive || !gesture || !canvasRef.current) return;
    if (gesture.pointerId !== event.pointerId) return;
    const point = pointFromEvent(
      canvasRef.current,
      event.clientX,
      event.clientY,
    );
    gestureRef.current = null;
    if (!point) return;
    if (gesture.moved) {
      emit({
        action: 'drag',
        x1: gesture.startX,
        y1: gesture.startY,
        x2: point.x,
        y2: point.y,
      });
      tapRef.current = null;
      return;
    }

    const now = performance.now();
    const previous = tapRef.current;
    if (
      previous &&
      now - previous.time < 320 &&
      Math.hypot(previous.x - point.x, previous.y - point.y) < 0.03
    ) {
      emit({ action: 'double_click', x: point.x, y: point.y });
      tapRef.current = null;
    } else {
      emit({ action: 'click', x: point.x, y: point.y });
      tapRef.current = { time: now, x: point.x, y: point.y };
    }
  };

  const onPointerCancel = () => {
    gestureRef.current = null;
  };

  const onWheel = (event: ReactWheelEvent<HTMLCanvasElement>) => {
    if (!interactive) return;
    event.preventDefault();
    const magnitude = Math.max(
      1,
      Math.min(5, Math.round(Math.abs(event.deltaY) / 120)),
    );
    const dy = (event.deltaY < 0 ? 1 : -1) * magnitude;
    emit({ action: 'scroll', dx: 0, dy });
  };

  if (!frame) {
    return (
      <div className="screen-placeholder">
        <span className="screen-placeholder-dot" />
        <span>CONNECTING</span>
      </div>
    );
  }
  return (
    <div className="screen-frame" ref={frameBoxRef}>
      <canvas
        ref={canvasRef}
        className={interactive ? 'screen-canvas interactive' : 'screen-canvas'}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerCancel}
        onWheel={onWheel}
        onContextMenu={(event) => {
          if (interactive) event.preventDefault();
        }}
      />
      {frame && (
        <div
          ref={overlayRef}
          className={maskMode ? 'screen-overlay drawing' : 'screen-overlay'}
          data-testid="screen-overlay"
          style={
            overlayRect
              ? {
                  left: `${overlayRect.left}px`,
                  top: `${overlayRect.top}px`,
                  width: `${overlayRect.width}px`,
                  height: `${overlayRect.height}px`,
                }
              : { left: 0, top: 0, width: '100%', height: '100%' }
          }
          onPointerDown={onOverlayPointerDown}
          onPointerMove={onOverlayPointerMove}
          onPointerUp={onOverlayPointerUp}
          onPointerCancel={onOverlayPointerUp}
        >
          {masksEnabled &&
            masks.map((mask) => (
            <div
              key={mask.id}
              className="privacy-mask active"
              style={{
                left: `${mask.x * 100}%`,
                top: `${mask.y * 100}%`,
                width: `${mask.w * 100}%`,
                height: `${mask.h * 100}%`,
              }}
            />
          ))}
          {draft && (
            <div
              className="privacy-mask draft"
              style={{
                left: `${draft.x * 100}%`,
                top: `${draft.y * 100}%`,
                width: `${draft.w * 100}%`,
                height: `${draft.h * 100}%`,
              }}
            />
          )}
          {preview?.kind === 'point' && (
            <div
              className="preview-point"
              data-testid="preview-point"
              style={{
                left: `${Number(preview.target.x ?? 0.5) * 100}%`,
                top: `${Number(preview.target.y ?? 0.5) * 100}%`,
              }}
              onPointerDown={(event) => startPreviewDrag(event, 'point')}
            >
              <span className="preview-ring" />
              <span className="preview-ring inner" />
              <span className="preview-crosshair" />
              <span className="preview-dot" />
              {preview.summary && (
                <span className="preview-chip">{preview.summary}</span>
              )}
            </div>
          )}
          {preview?.kind === 'drag' && (
            <>
              <svg className="preview-drag" data-testid="preview-drag">
                <line
                  x1={`${Number(preview.target.x1 ?? 0.5) * 100}%`}
                  y1={`${Number(preview.target.y1 ?? 0.5) * 100}%`}
                  x2={`${Number(preview.target.x2 ?? 0.5) * 100}%`}
                  y2={`${Number(preview.target.y2 ?? 0.5) * 100}%`}
                />
                <circle
                  className="preview-handle"
                  cx={`${Number(preview.target.x1 ?? 0.5) * 100}%`}
                  cy={`${Number(preview.target.y1 ?? 0.5) * 100}%`}
                  r={7}
                  onPointerDown={(event) => startPreviewDrag(event, 'start')}
                />
                <circle
                  className="preview-handle"
                  cx={`${Number(preview.target.x2 ?? 0.5) * 100}%`}
                  cy={`${Number(preview.target.y2 ?? 0.5) * 100}%`}
                  r={7}
                  onPointerDown={(event) => startPreviewDrag(event, 'end')}
                />
              </svg>
              {preview.summary && (
                <span
                  className="preview-chip"
                  style={{
                    left: `${((Number(preview.target.x1 ?? 0.5) + Number(preview.target.x2 ?? 0.5)) / 2) * 100}%`,
                    top: `${((Number(preview.target.y1 ?? 0.5) + Number(preview.target.y2 ?? 0.5)) / 2) * 100}%`,
                  }}
                >
                  {preview.summary}
                </span>
              )}
            </>
          )}
          {preview?.kind === 'scroll' && (
            <div className="preview-scroll" data-testid="preview-scroll">
              {Number(preview.target.dy ?? 0) >= 0 ? '↑' : '↓'}
              <span>{Math.abs(Number(preview.target.dy ?? 0))}</span>
              {preview.summary && (
                <span className="preview-chip inline">{preview.summary}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
