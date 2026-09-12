import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { danmakuText, eventStateClass } from '../eventText';
import type {
  ControlEvent,
  DanmakuDensity,
  DanmakuIntensity,
  DanmakuSize,
} from '../types';

interface Props {
  events: ControlEvent[];
  density: DanmakuDensity;
  size: DanmakuSize;
  intensity: DanmakuIntensity;
}

interface DanmakuItem {
  key: number;
  event: ControlEvent;
  lane: number;
}

const LANES = 3;
const DURATION_MS = 7000;
const FONT_SIZES: Record<DanmakuSize, string> = {
  small: '12px',
  medium: '14px',
  large: '17px',
};

function passes(event: ControlEvent, density: DanmakuDensity): boolean {
  if (event.type === 'approval_request') return true;
  if (event.type === 'action_proposal') return true;
  if (event.type === 'approval_resolved') return false;
  if (
    event.type === 'action_resolved' ||
    event.type === 'privacy_masks_changed' ||
    event.type === 'trust_changed'
  ) {
    return false;
  }
  if (density === 'all') return true;
  const state = event.type === 'agent_status' ? event.state : event.type;
  if (density === 'minimal') {
    return ['done', 'error', 'cancelled', 'cancelling', 'limit'].includes(state);
  }
  return true;
}

export function DanmakuOverlay({ events, density, size, intensity }: Props) {
  const [items, setItems] = useState<DanmakuItem[]>([]);
  const lastSeenRef = useRef(-1);
  const laneRef = useRef(0);
  const keyRef = useRef(0);
  const timersRef = useRef<number[]>([]);

  useEffect(() => {
    if (!events.length) return;
    const start = Math.max(0, lastSeenRef.current + 1);
    if (start >= events.length) return;
    lastSeenRef.current = events.length - 1;

    const spawned = events
      .slice(start)
      .filter((event) => passes(event, density))
      .map((event) => {
        const lane = laneRef.current;
        laneRef.current = (lane + 1) % LANES;
        return { key: keyRef.current++, event, lane };
      });
    if (!spawned.length) return;

    setItems((previous) => [...previous, ...spawned].slice(-10));
    for (const item of spawned) {
      const timer = window.setTimeout(() => {
        timersRef.current = timersRef.current.filter(
          (value) => value !== timer,
        );
        setItems((previous) =>
          previous.filter((current) => current.key !== item.key),
        );
      }, DURATION_MS);
      timersRef.current.push(timer);
    }
  }, [events, density]);

  useEffect(
    () => () => {
      for (const timer of timersRef.current) window.clearTimeout(timer);
    },
    [],
  );

  if (!items.length) return null;

  return (
    <div className="danmaku-overlay" aria-hidden="true">
      {items.map((item) => (
        <div
          key={item.key}
          className={`danmaku-item danmaku-${intensity}`}
          data-state={eventStateClass(item.event)}
          style={
            {
              '--lane': item.lane,
              '--size': FONT_SIZES[size],
            } as CSSProperties
          }
        >
          {danmakuText(item.event)}
        </div>
      ))}
    </div>
  );
}
