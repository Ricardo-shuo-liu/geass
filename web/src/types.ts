export type AgentState =
  | 'accepted'
  | 'thinking'
  | 'acting'
  | 'acted'
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
}

export interface AgentResult {
  type: 'agent_result';
  state: string;
  message: string;
}

export type ControlEvent = AgentStatus | AgentResult;

