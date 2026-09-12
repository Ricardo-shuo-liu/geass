import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { TrustSettings } from '../types';
import { TrustPanel } from './TrustPanel';

const settings: TrustSettings = {
  mode: 'smart',
  visual_delay_ms: 600,
  overrides: { open_terminal: 'confirm' },
  task_allow_all: false,
};

afterEach(cleanup);

describe('TrustPanel', () => {
  it('switches mode and privacy toggle', () => {
    const onUpdate = vi.fn();
    const onToggleMasks = vi.fn();
    render(
      <TrustPanel
        settings={settings}
        masks={[{ id: 'm1', x: 0.1, y: 0.1, w: 0.2, h: 0.2 }]}
        masksEnabled={false}
        maskMode={false}
        suggestions={[]}
        detecting={false}
        onUpdate={onUpdate}
        onToggleMaskMode={vi.fn()}
        onToggleMasks={onToggleMasks}
        onDeleteMask={vi.fn()}
        onClearMasks={vi.fn()}
        onDetect={vi.fn()}
        onApplySuggestion={vi.fn()}
        onApplyAllSuggestions={vi.fn()}
        onDismissSuggestions={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '全部确认' }));
    expect(onUpdate).toHaveBeenCalledWith({ mode: 'confirm' });

    fireEvent.click(screen.getByRole('checkbox', { name: /启用遮罩/ }));
    expect(onToggleMasks).toHaveBeenCalledWith(true);
  });

  it('removes an override', () => {
    const onUpdate = vi.fn();
    render(
      <TrustPanel
        settings={settings}
        masks={[]}
        masksEnabled
        maskMode={false}
        suggestions={[]}
        detecting={false}
        onUpdate={onUpdate}
        onToggleMaskMode={vi.fn()}
        onToggleMasks={vi.fn()}
        onDeleteMask={vi.fn()}
        onClearMasks={vi.fn()}
        onDetect={vi.fn()}
        onApplySuggestion={vi.fn()}
        onApplyAllSuggestions={vi.fn()}
        onDismissSuggestions={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '移除 open_terminal 覆盖' }));
    expect(onUpdate).toHaveBeenCalledWith({ overrides: { open_terminal: null } });
  });

  it('lists detected regions and applies one', () => {
    const onApplySuggestion = vi.fn();
    const onDetect = vi.fn();
    render(
      <TrustPanel
        settings={settings}
        masks={[]}
        masksEnabled={false}
        maskMode={false}
        suggestions={[
          { x: 0.1, y: 0.2, w: 0.3, h: 0.1, source: 'password', label: '密码输入框' },
        ]}
        detecting={false}
        onUpdate={vi.fn()}
        onToggleMaskMode={vi.fn()}
        onToggleMasks={vi.fn()}
        onDeleteMask={vi.fn()}
        onClearMasks={vi.fn()}
        onDetect={onDetect}
        onApplySuggestion={onApplySuggestion}
        onApplyAllSuggestions={vi.fn()}
        onDismissSuggestions={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '自动识别敏感区域' }));
    expect(onDetect).toHaveBeenCalled();
    expect(screen.getByText(/密码框 · 密码输入框/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '应用' }));
    expect(onApplySuggestion).toHaveBeenCalledWith(0);
  });
});
