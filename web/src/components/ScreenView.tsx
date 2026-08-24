import { useEffect, useRef } from 'react';
import type {
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
} from 'react';
import type { ManualAction } from '../types';

const MOVE_THROTTLE_MS = 20;
const TAP_DISTANCE = 0.012;
const MOVE_THRESHOLD = 0.0008;

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
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
}: {
  frame: Blob | null;
  interactive?: boolean;
  onManualAction?: (action: ManualAction) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<Blob | null>(null);
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
      bitmap.close();
      bitmap = null;
    }

    draw().catch(() => {});
    return () => {
      disposed = true;
      if (bitmap) bitmap.close();
    };
  }, [frame]);

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
  );
}
