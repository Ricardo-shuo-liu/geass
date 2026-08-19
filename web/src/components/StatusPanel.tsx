import type { ControlEvent } from '../types';

interface Props {
  events: ControlEvent[];
  busy: boolean;
}

export function StatusPanel({ events, busy }: Props) {
  const recent = events.slice(-12);
  return (
    <div className="status-panel">
      <div className="status-head">
        <span className={`status-badge ${busy ? 'busy' : 'idle'}`}>
          {busy ? '执行中' : '空闲'}
        </span>
        <span className="status-hint">可随时点击「停止」中断 Agent</span>
      </div>
      <ul>
        {recent.map((event, index) => (
          <li key={`${event.type}-${index}`} className={`status-${event.state}`}>
            {event.type === 'agent_result'
              ? `[结果] ${event.message}`
              : `[${event.state}${event.step ? ` #${event.step}` : ''}${
                  event.tool ? ` ${event.tool}` : ''
                }] ${event.message ?? ''}`}
          </li>
        ))}
      </ul>
    </div>
  );
}

