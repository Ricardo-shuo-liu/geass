import { useEffect, useRef } from 'react';
import { renderLine } from '../eventText';
import type { ControlEvent } from '../types';

interface Props {
  open: boolean;
  busy: boolean;
  events: ControlEvent[];
  onClose: () => void;
}

function rowClass(event: ControlEvent): string {
  if (event.type === 'agent_status') return `log-${event.state}`;
  if (event.type === 'approval_request') return 'log-approval-request';
  if (event.type === 'approval_resolved') {
    return event.approved ? 'log-approval-ok' : 'log-approval-denied';
  }
  if (event.type === 'evolution_status') return 'log-evolution';
  if (event.type === 'error') return 'log-error';
  return 'log-result';
}

export function LogDrawer({ open, busy, events, onClose }: Props) {
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [events, open]);

  return (
    <div
      className={`drawer-scrim ${open ? 'open' : ''}`}
      onClick={onClose}
      aria-hidden={!open}
    >
      <aside
        className="log-drawer"
        role="log"
        aria-live="polite"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-head">
          <div className="drawer-title-row">
            <span className="drawer-title">流程日志</span>
            <span className={`chip ${busy ? 'busy' : 'idle'}`}>
              <span className="dot" />
              {busy ? '执行中' : '空闲'}
            </span>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="关闭日志"
          >
            ✕
          </button>
        </div>
        <ul ref={listRef}>
          {events.length === 0 && <li className="log-empty">暂无消息</li>}
          {events.map((event, index) => (
            <li key={`${event.type}-${index}`} className={rowClass(event)}>
              {event._time && <span className="log-time">{event._time}</span>}
              <span className="log-line">{renderLine(event)}</span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
