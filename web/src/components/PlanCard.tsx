import type { TaskPlan } from '../types';

interface Props {
  plan: TaskPlan;
  onClose: () => void;
}

export default function PlanCard({ plan, onClose }: Props) {
  const done = plan.steps.slice(0, Math.max(0, plan.current_step - 1));
  const current = plan.steps[plan.current_step - 1] ?? null;
  const pending = plan.steps.slice(plan.current_step);

  return (
    <div className="plan-card">
      <div className="plan-card-head">
        <span className={`plan-badge ${plan.difficulty}`}>
          {plan.difficulty === 'hard' ? '困难任务' : '简单任务'}
        </span>
        <span className="plan-goal">{plan.goal}</span>
        <button
          type="button"
          className="plan-close"
          onClick={onClose}
          aria-label="收起计划"
        >
          ×
        </button>
      </div>
      <ol className="plan-steps">
        {done.map((step, index) => (
          <li key={`done-${index}`} className="done">
            <span className="marker">✓</span>
            {step}
          </li>
        ))}
        {current && (
          <li className="current">
            <span className="marker">▶</span>
            {current}
          </li>
        )}
        {pending.map((step, index) => (
          <li key={`pending-${index}`} className="pending">
            <span className="marker">·</span>
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}
