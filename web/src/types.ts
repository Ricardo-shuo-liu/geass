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

export interface ScheduleJob {
  id: string;
  command: string;
  run_at: number;
  created_at: number;
  persistent?: boolean;
  status: 'pending' | 'running' | 'done' | 'error';
  retry_at?: number;
  message?: string;
  updated_at?: number;
}

export interface ScheduleStatus {
  type: 'schedule_status';
  job?: ScheduleJob;
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
  | ScheduleStatus
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

export interface MemoryEntryResource {
  key: string;
  value: string;
  updated_at?: number;
}

export interface RagSourceResource {
  id: string;
  name: string;
  root: string;
  exts: string[];
  mode: string;
  enabled: boolean;
  needs_reindex?: boolean;
  embedding_model?: string;
  embedding_dim?: number;
  files: number;
  chunks: number;
}

export interface SkillResource {
  name: string;
  description: string;
  path: string;
  system: boolean;
}

export interface RotResource {
  name: string;
  description: string;
  role: string;
  enabled: boolean;
}

export interface ScheduleJobResource {
  id: string;
  command: string;
  run_at: number;
  created_at: number;
  persistent?: boolean;
  status: string;
  message?: string;
}

export interface BackgroundTaskResource {
  id: string;
  command: string;
  created_at: number;
  started_at?: number;
  finished_at?: number;
  status: string;
  message?: string;
  result?: { state?: string; message?: string };
}

export interface McpToolResource {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  input_schema?: Record<string, unknown>;
}

export interface McpServerResource {
  id: string;
  name: string;
  transport: 'stdio' | 'http';
  enabled: boolean;
  verified: boolean;
  last_test_at?: number | null;
  last_error?: string | null;
  command?: string;
  args?: string[];
  cwd?: string;
  url?: string;
  env_keys?: string[];
  header_keys?: string[];
  tools: McpToolResource[];
}

export interface ResourceSummary {
  memory: { enabled: boolean; entries: MemoryEntryResource[] };
  rag: { enabled: boolean; sources: RagSourceResource[] };
  skills: SkillResource[];
  pot: { enabled: boolean; cot: string; rots: RotResource[] };
  schedule: { jobs: ScheduleJobResource[] };
  background: {
    enabled: boolean;
    max: number;
    tasks: BackgroundTaskResource[];
  };
  mcp: { enabled: boolean; servers: McpServerResource[] };
}

export interface McpAddInput {
  name: string;
  transport: 'stdio' | 'http';
  command?: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}
