export type AgentState =
  | 'accepted'
  | 'thinking'
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
  _time?: string;
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
  | ServerError;

export type DanmakuDensity = 'all' | 'key' | 'minimal';

export type DanmakuSize = 'small' | 'medium' | 'large';

export type DanmakuIntensity = 'light' | 'standard' | 'strong';
