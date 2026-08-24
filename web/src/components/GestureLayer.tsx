import { useRef } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

interface Props {
  onDoubleTap: () => void;
  onSwipeUp: () => void;
}

const TAP_WINDOW_MS = 320;
const TAP_MOVE_PX = 10;
const SWIPE_UP_PX = 56;

export function GestureLayer({ onDoubleTap, onSwipeUp }: Props) {
  const gestureRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    moved: boolean;
  } | null>(null);
  const tapRef = useRef<{ time: number; x: number; y: number } | null>(null);

  const down = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture?.(event.pointerId);
    gestureRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      lastX: event.clientX,
      lastY: event.clientY,
      moved: false,
    };
  };

  const move = (event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    gesture.lastX = event.clientX;
    gesture.lastY = event.clientY;
    if (
      Math.hypot(
        event.clientX - gesture.startX,
        event.clientY - gesture.startY,
      ) > TAP_MOVE_PX
    ) {
      gesture.moved = true;
    }
  };

  const up = (event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    gestureRef.current = null;

    if (!gesture.moved) {
      const now = performance.now();
      const previous = tapRef.current;
      if (
        previous &&
        now - previous.time < TAP_WINDOW_MS &&
        Math.hypot(
          previous.x - event.clientX,
          previous.y - event.clientY,
        ) < TAP_MOVE_PX
      ) {
        tapRef.current = null;
        onDoubleTap();
        return;
      }
      tapRef.current = {
        time: now,
        x: event.clientX,
        y: event.clientY,
      };
      return;
    }

    tapRef.current = null;
    const deltaX = gesture.lastX - gesture.startX;
    const deltaY = gesture.lastY - gesture.startY;
    if (
      deltaY < -SWIPE_UP_PX &&
      Math.abs(deltaY) > Math.abs(deltaX) * 1.2
    ) {
      onSwipeUp();
    }
  };

  return (
    <div
      className="gesture-layer"
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={() => {
        gestureRef.current = null;
      }}
    />
  );
}
