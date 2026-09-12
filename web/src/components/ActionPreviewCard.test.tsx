import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ActionProposal } from '../types';
import { ActionPreviewCard, ActionPreviewStrip } from './ActionPreviewCard';

function proposal(overrides: Partial<ActionProposal> = {}): ActionProposal {
  return {
    type: 'action_proposal',
    id: 'p1',
    tool: 'type_text',
    kind: 'text',
    target: { text: 'hello' },
    summary: '输入文本：hello',
    decision_required: true,
    delay_ms: 0,
    step: 2,
    total_steps: 5,
    undoable: false,
    expires_in: 30,
    ...overrides,
  };
}

afterEach(cleanup);

describe('ActionPreviewCard', () => {
  it('edits the target and approves', () => {
    const onTargetChange = vi.fn();
    const onApprove = vi.fn();
    render(
      <ActionPreviewCard
        proposal={proposal()}
        target={{ text: 'hello' }}
        onTargetChange={onTargetChange}
        onApprove={onApprove}
        onDeny={vi.fn()}
        onAllowToolAlways={vi.fn()}
        onAllowTask={vi.fn()}
      />,
    );

    expect(screen.getByText('步骤 2/5')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hi' } });
    expect(onTargetChange).toHaveBeenCalledWith({ text: 'hi' });
    fireEvent.click(screen.getByRole('button', { name: '执行' }));
    expect(onApprove).toHaveBeenCalled();
  });

  it('renders a strip with intercept for auto proposals', () => {
    const onIntercept = vi.fn();
    render(
      <ActionPreviewStrip
        proposal={proposal({ decision_required: false, delay_ms: 600 })}
        onIntercept={onIntercept}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '拦截' }));
    expect(onIntercept).toHaveBeenCalled();
  });
});
