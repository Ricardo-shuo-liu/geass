import type { ControlEvent } from './types';

export const STATE_LABELS: Record<string, string> = {
  accepted: '命令',
  thinking: '思考',
  acting: '执行',
  acted: 'OK',
  awaiting_approval: '待审核',
  done: '完成',
  error: '错误',
  cancelled: '中断',
  cancelling: '中断',
  limit: '上限',
  busy: '忙碌',
};

export function renderLine(event: ControlEvent): string {
  if (event.type === 'agent_result') {
    return `[结果] ${event.message}`;
  }
  if (event.type === 'approval_request') {
    return `[审核] ${event.command}（${event.reason ?? '命中安全规则'}）`;
  }
  if (event.type === 'approval_resolved') {
    return `[审核${event.approved ? '通过' : '拒绝'}]${event.reason ? ` ${event.reason}` : ''}`;
  }
  if (event.type === 'error') {
    return `[错误] ${event.message ?? ''}`;
  }
  const label = STATE_LABELS[event.state] ?? event.state;
  const parts = [label];
  if (event.step) parts.push(`#${event.step}`);
  if (event.tool) parts.push(event.tool);
  return `[${parts.join(' · ')}] ${event.message ?? ''}`;
}

export function danmakuText(event: ControlEvent): string {
  if (event.type === 'approval_request') {
    return `待审核 · ${event.command}`;
  }
  if (event.type === 'approval_resolved') {
    return event.approved ? '审核通过' : '审核已拒绝';
  }
  if (event.type === 'agent_result') {
    return `完成 · ${event.message}`;
  }
  if (event.type === 'error') {
    return `错误 · ${event.message ?? ''}`;
  }
  const label = STATE_LABELS[event.state] ?? event.state;
  const parts = [label];
  if (event.tool) parts.push(event.tool);
  return `${parts.join(' · ')} ${event.message ?? ''}`.trim();
}

export function eventStateClass(event: ControlEvent): string {
  if (event.type === 'approval_request') return 'approval-pending';
  if (event.type === 'approval_resolved') {
    return event.approved ? 'approval-ok' : 'approval-pending';
  }
  if (event.type === 'error') return 'error';
  if (event.type === 'agent_result') return event.state;
  return event.state;
}
