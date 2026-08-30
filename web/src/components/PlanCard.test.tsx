import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TaskPlan } from '../types';
import PlanCard from './PlanCard';

describe('PlanCard', () => {
  it('renders goal, completed, current and pending steps', () => {
    const plan: TaskPlan = {
      difficulty: 'hard',
      goal: '打开浏览器',
      steps: ['第一步', '第二步', '第三步'],
      current_step: 2,
    };

    render(<PlanCard plan={plan} onClose={() => {}} />);

    expect(screen.getByText('困难任务')).toBeInTheDocument();
    expect(screen.getByText('打开浏览器')).toBeInTheDocument();
    expect(screen.getByText('第一步')).toBeInTheDocument();
    expect(screen.getByText('第二步')).toBeInTheDocument();
    expect(screen.getByText('第三步')).toBeInTheDocument();
    expect(screen.getByText('▶')).toBeInTheDocument();
  });
});
