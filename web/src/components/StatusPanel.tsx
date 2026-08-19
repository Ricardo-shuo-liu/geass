import type { ControlEvent } from '../types';

interface Props {
  events: ControlEvent[];
  busy: boolean;
}

const STATE_LABELS: Record<string, string> = {
  accepted: '已接收',
  thinking: '思考',
  acting: '执行',
  acted: 'OK',
  done: '完成',
  error: '错误',
  cancelled: '中断',
  cancelling: '中断',
  limit: '上限',
  busy: '忙碌',
};

function renderLine(event: ControlEvent): string {
  if (event.type === 'agent_result') {
    return `[结果] ${event.message}`;
  }
  const label = STATE_LABELS[event.state] ?? event.state;
  const parts = [label];
  if (event.step) parts.push(`#${event.step}`);
  if (event.tool) parts.push(event.tool);
  return `[${parts.join(' · ')}] ${event.message ?? ''}`;
}

export function StatusPanel({ events, busy }: Props) {
  const recent = events.slice(-12);
  return (
    <div className="status-panel">
      <div className="status-head">
        <span className={`status-badge ${busy ? 'busy' : 'idle'}`}>
          <span className="status-dot" />
          {busy ? '执行中' : '空闲'}
        </span>
      </div>
      <ul>
        {recent.length === 0 && <li className="status-empty">暂无消息</li>}
        {recent.map((event, index) => {
          const line = renderLine(event);
          return (
            <li key={`${event.type}-${index}`} className={`status-${event.state}`}>
              {event._time && <span className="status-time">{event._time}</span>}
              <span className="status-line">{line}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
