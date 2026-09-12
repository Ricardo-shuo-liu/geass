import { useEffect, useState } from 'react';
import type { ActionProposal } from '../types';

const KIND_ICON: Record<ActionProposal['kind'], string> = {
  point: '◎',
  drag: '↗',
  scroll: '↕',
  text: '⌨',
  key: '⌘',
  command: '▮',
  terminal: '▮',
  url: '🔗',
  generic: '⚙',
};

interface Props {
  proposal: ActionProposal;
  target: Record<string, unknown>;
  resolved?: { approved: boolean; auto: boolean } | null;
  onTargetChange: (target: Record<string, unknown>) => void;
  onApprove: () => void;
  onDeny: () => void;
  onAllowToolAlways: () => void;
  onAllowTask: () => void;
}

function stepLabel(proposal: ActionProposal): string {
  if (proposal.total_steps > 0) {
    return `步骤 ${proposal.step || proposal.total_steps}/${proposal.total_steps}`;
  }
  return proposal.step > 0 ? `步骤 ${proposal.step}` : '当前动作';
}

function useCountdown(seconds: number): number {
  const [left, setLeft] = useState(Math.max(0, Math.round(seconds)));
  useEffect(() => {
    setLeft(Math.max(0, Math.round(seconds)));
    const timer = window.setInterval(() => {
      setLeft((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);
  return left;
}

export function ActionPreviewCard({
  proposal,
  target,
  resolved = null,
  onTargetChange,
  onApprove,
  onDeny,
  onAllowToolAlways,
  onAllowTask,
}: Props) {
  const left = useCountdown(proposal.expires_in);
  const set = (key: string, value: unknown) =>
    onTargetChange({ ...target, [key]: value });

  return (
    <section className="action-card" role="alertdialog" aria-label="动作预览">
      <div className="action-card-head">
        <span className="action-kind">{KIND_ICON[proposal.kind] ?? '◎'}</span>
        <span className="action-step">{stepLabel(proposal)}</span>
        <span className="action-tool">{proposal.tool}</span>
        <span className="countdown">{left}s</span>
      </div>
      {!resolved && (
        <div className="action-progress">
          <span style={{ animationDuration: `${Math.max(1, proposal.expires_in)}s` }} />
        </div>
      )}
      <p className="action-summary">{proposal.summary}</p>
      {proposal.security_reason && (
        <p className="action-warning">⚠ 命中安全规则：{proposal.security_reason}</p>
      )}
      <div className="action-fields">
        {(proposal.kind === 'text' ||
          proposal.kind === 'command' ||
          proposal.kind === 'terminal') && (
          <textarea
            value={String(target.text ?? target.command ?? '')}
            onChange={(event) =>
              set(proposal.kind === 'command' ? 'command' : 'text', event.target.value)
            }
            rows={3}
          />
        )}
        {proposal.kind === 'key' && (
          <input
            value={String(target.combo ?? '')}
            onChange={(event) => set('combo', event.target.value)}
            placeholder="按键组合，如 ctrl+s"
          />
        )}
        {proposal.kind === 'url' && (
          <input
            value={String(target.url ?? '')}
            onChange={(event) => set('url', event.target.value)}
            placeholder="https://example.com"
          />
        )}
        {proposal.kind === 'scroll' && (
          <div className="action-scroll-row">
            <label>
              dx
              <input
                type="number"
                value={Number(target.dx ?? 0)}
                onChange={(event) => set('dx', Number(event.target.value))}
              />
            </label>
            <label>
              dy
              <input
                type="number"
                value={Number(target.dy ?? 0)}
                onChange={(event) => set('dy', Number(event.target.value))}
              />
            </label>
          </div>
        )}
        {(proposal.kind === 'point' || proposal.kind === 'drag') && (
          <p className="action-hint">在画面上拖动标记可直接修正目标位置</p>
        )}
        {proposal.kind === 'generic' && (
          <pre className="action-generic">
            {JSON.stringify(target.args ?? target, null, 2)}
          </pre>
        )}
      </div>
      {resolved ? (
        <p className={resolved.approved ? 'action-done' : 'action-warning'}>
          {resolved.approved ? '✓ 已执行' : '✗ 已拒绝'}
          {resolved.auto ? '（自动）' : ''}
        </p>
      ) : (
        <>
          <div className="action-actions">
            <button type="button" className="approve" onClick={onApprove}>
              执行
            </button>
            <button type="button" className="deny" onClick={onDeny}>
              拒绝
            </button>
          </div>
          <div className="action-secondary">
            <button type="button" onClick={onAllowToolAlways}>
              始终允许 {proposal.tool}
            </button>
            <button type="button" onClick={onAllowTask}>
              本任务全部放行
            </button>
          </div>
        </>
      )}
    </section>
  );
}

interface StripProps {
  proposal: ActionProposal;
  onIntercept: () => void;
  resolved?: { approved: boolean; auto: boolean } | null;
}

export function ActionPreviewStrip({
  proposal,
  onIntercept,
  resolved = null,
}: StripProps) {
  const seconds = Math.max(0, Math.ceil(proposal.delay_ms / 1000));
  const left = useCountdown(seconds);
  return (
    <div className="action-strip" data-testid="action-strip">
      <span className="action-kind">{KIND_ICON[proposal.kind] ?? '◎'}</span>
      <span className="action-step">{stepLabel(proposal)}</span>
      <span className="action-summary">{proposal.summary}</span>
      {resolved ? (
        <span className={resolved.approved ? 'action-done' : 'action-warning'}>
          {resolved.approved ? '✓ 已执行' : '✗ 已拦截'}
        </span>
      ) : (
        <>
          <span className="action-countdown">
            {seconds > 0 ? `${left}s` : '执行中'}
          </span>
          <button type="button" className="deny" onClick={onIntercept}>
            拦截
          </button>
        </>
      )}
      {!resolved && (
        <span
          className="action-strip-progress"
          style={{ animationDuration: `${Math.max(120, proposal.delay_ms)}ms` }}
        />
      )}
    </div>
  );
}
