import { describe, expect, it } from 'vitest';

import { danmakuText, eventStateClass, renderLine } from './eventText';

describe('eventText', () => {
  it('renders approval and result lines', () => {
    expect(
      renderLine({
        type: 'approval_request',
        id: 'a-1',
        command: 'sudo ls',
        reason: '提权',
      }),
    ).toBe('[审核] sudo ls（提权）');

    expect(renderLine({ type: 'agent_result', state: 'done', message: '完成' })).toBe(
      '[结果] 完成',
    );
  });

  it('renders a planned agent status with goal and step count', () => {
    expect(
      renderLine({
        type: 'agent_status',
        state: 'planned',
        step: 1,
        message: '计划',
        plan: { difficulty: 'hard', goal: '打开浏览器', steps: ['a', 'b'], current_step: 1 },
      }),
    ).toBe('[计划·困难] 打开浏览器（2 步）');
  });

  it('falls back to state label with step and tool', () => {
    expect(
      renderLine({ type: 'agent_status', state: 'acting', step: 3, tool: 'click', message: '执行' }),
    ).toBe('[执行 · #3 · click] 执行');
  });

  it('builds danmaku text and state class', () => {
    expect(
      danmakuText({
        type: 'approval_request',
        id: 'a-1',
        command: 'rm -rf /',
      }),
    ).toBe('待审核 · rm -rf /');

    expect(eventStateClass({ type: 'approval_request', id: 'a-1', command: 'x' })).toBe(
      'approval-pending',
    );
    expect(eventStateClass({ type: 'error', message: 'x' })).toBe('error');
  });
});
