import { useEffect, useState } from 'react';
import type { ApprovalRequest } from '../types';

interface Props {
  approval: ApprovalRequest;
  onApprove: () => void;
  onDeny: () => void;
}

export function ApprovalModal({ approval, onApprove, onDeny }: Props) {
  const total = Math.max(1, Math.round(approval.expires_in ?? 30));
  const [left, setLeft] = useState(total);

  useEffect(() => {
    setLeft(total);
    const timer = window.setInterval(() => {
      setLeft((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [approval.id, total]);

  return (
    <div className="approval-backdrop">
      <section
        className="approval-card"
        role="alertdialog"
        aria-modal="true"
        aria-label="安全审核"
      >
        <div className="approval-head">
          <span className="approval-icon">⚠</span>
          <h2>安全审核</h2>
          <span className="countdown">{left}s</span>
        </div>
        <p className="approval-reason">
          {approval.reason ?? '该命令可能造成破坏性影响，需要你确认'}
        </p>
        <pre className="approval-command">{approval.command}</pre>
        <div className="approval-actions">
          <button type="button" className="approve" onClick={onApprove}>
            允许执行
          </button>
          <button type="button" className="deny" onClick={onDeny}>
            拒绝
          </button>
        </div>
      </section>
    </div>
  );
}
