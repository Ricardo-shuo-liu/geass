import type { ControlEvent } from './types';

export const STATE_LABELS: Record<string, string> = {
  accepted: '命令',
  thinking: '思考',
  planned: '计划',
  acting: '执行',
  acted: 'OK',
  awaiting_approval: '待审核',
  awaiting_action: '待确认',
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
  if (event.type === 'action_proposal') {
    return `[预览${event.decision_required ? '·待确认' : '·自动'}] ${event.summary}`;
  }
  if (event.type === 'action_resolved') {
    return `[预览${event.approved ? '通过' : '拒绝'}]${event.reason ? ` ${event.reason}` : ''}`;
  }
  if (event.type === 'privacy_masks_changed') {
    return `[遮罩] ${event.enabled ? '已启用' : '已关闭'} · ${event.masks.length} 个区域`;
  }
  if (event.type === 'trust_changed') {
    return `[信任] 模式 ${event.mode} · 延迟 ${event.visual_delay_ms}ms`;
  }
  if (event.type === 'evolution_status') {
    return `[进化] ${event.name ? `生成技能 ${event.name}` : event.message}`;
  }
  if (event.type === 'schedule_status') {
    return `[定时] ${event.message}`;
  }
  if (event.type === 'error') {
    return `[错误] ${event.message ?? ''}`;
  }
  if (event.type === 'agent_status' && event.state === 'planned' && event.plan) {
    return `[计划·${event.plan.difficulty === 'hard' ? '困难' : '简单'}] ${event.plan.goal}（${event.plan.steps.length} 步）`;
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
  if (event.type === 'action_proposal') {
    return `预览 · ${event.summary}`;
  }
  if (event.type === 'action_resolved') {
    return event.approved ? '预览通过' : '预览拦截';
  }
  if (event.type === 'privacy_masks_changed' || event.type === 'trust_changed') {
    return '';
  }
  if (event.type === 'evolution_status') {
    return event.name ? `进化 · ${event.name}` : `进化 · ${event.message}`;
  }
  if (event.type === 'schedule_status') {
    return `定时 · ${event.message}`;
  }
  if (event.type === 'agent_result') {
    return `完成 · ${event.message}`;
  }
  if (event.type === 'error') {
    return `错误 · ${event.message ?? ''}`;
  }
  if (event.type === 'agent_status' && event.state === 'planned' && event.plan) {
    return `计划 · ${event.plan.difficulty === 'hard' ? '困难' : '简单'} · ${event.plan.goal}`;
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
  if (event.type === 'action_proposal') return 'acting';
  if (event.type === 'action_resolved') {
    return event.approved ? 'approval-ok' : 'approval-pending';
  }
  if (event.type === 'privacy_masks_changed' || event.type === 'trust_changed') {
    return 'acted';
  }
  if (event.type === 'evolution_status') return 'evolution';
  if (event.type === 'schedule_status') return 'schedule';
  if (event.type === 'error') return 'error';
  if (event.type === 'agent_result') return event.state;
  return event.state;
}
