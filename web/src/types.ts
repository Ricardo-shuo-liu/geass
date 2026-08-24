export type AgentState =
  | 'accepted'
  | 'thinking'
  | 'planned'
  | 'acting'
  | 'acted'
  | 'awaiting_approval'
  | 'done'
  | 'error'
  | 'cancelled'
  | 'cancelling'
  | 'limit'
  | 'busy';

export interface AgentStatus {
  type: 'agent_status';
  state: AgentState;
  step: number;
  tool?: string | null;
  message?: string;
  plan?: TaskPlan | null;
  _time?: string;
}

export interface TaskPlan {
  difficulty: 'easy' | 'hard';
  goal: string;
  steps: string[];
  current_step: number;
}

export interface AgentResult {
  type: 'agent_result';
  state: string;
  message: string;
  _time?: string;
}

export interface ApprovalRequest {
  type: 'approval_request';
  id: string;
  tool?: string;
  command: string;
  reason?: string;
  expires_in?: number;
  _time?: string;
}

export interface ApprovalResolved {
  type: 'approval_resolved';
  id: string;
  approved: boolean;
  reason?: string;
  _time?: string;
}

export interface EvolutionStatus {
  type: 'evolution_status';
  created: boolean;
  name?: string;
  description?: string;
  message: string;
  _time?: string;
}

export interface ServerError {
  type: 'error';
  message?: string;
  _time?: string;
}

export type ControlEvent =
  | AgentStatus
  | AgentResult
  | ApprovalRequest
  | ApprovalResolved
  | EvolutionStatus
  | ServerError;

export type DanmakuDensity = 'all' | 'key' | 'minimal';

export type DanmakuSize = 'small' | 'medium' | 'large';

export type DanmakuIntensity = 'light' | 'standard' | 'strong';

export type ManualAction =
  | { action: 'move'; x: number; y: number }
  | {
      action: 'click';
      x: number;
      y: number;
      button?: 'left' | 'right' | 'middle';
    }
  | { action: 'double_click'; x: number; y: number }
  | { action: 'right_click'; x: number; y: number }
  | { action: 'drag'; x1: number; y1: number; x2: number; y2: number }
  | { action: 'scroll'; dx: number; dy: number }
  | { action: 'key'; combo: string }
  | { action: 'type'; text: string };
