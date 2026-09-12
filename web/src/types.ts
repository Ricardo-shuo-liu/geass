export type AgentState =
  | 'accepted'
  | 'thinking'
  | 'planned'
  | 'acting'
  | 'acted'
  | 'awaiting_approval'
  | 'awaiting_action'
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

export interface PrivacyMask {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PrivacyMasksChanged {
  type: 'privacy_masks_changed';
  enabled: boolean;
  masks: PrivacyMask[];
  _time?: string;
}

export interface SensitiveRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  source: 'password' | 'keyword';
  label: string;
}

export interface SensitiveDetectResult {
  regions: SensitiveRegion[];
  sources: { password_fields: number; keyword_matches: number };
  keywords: string[];
}

export type PreviewMode = 'smart' | 'confirm' | 'off';

export interface TrustSettings {
  mode: PreviewMode;
  visual_delay_ms: number;
  overrides: Record<string, 'auto' | 'confirm'>;
  task_allow_all: boolean;
}

export interface TrustChanged extends TrustSettings {
  type: 'trust_changed';
  _time?: string;
}

export type ActionKind =
  | 'point'
  | 'drag'
  | 'scroll'
  | 'text'
  | 'key'
  | 'command'
  | 'terminal'
  | 'url'
  | 'generic';

export interface ActionProposal {
  type: 'action_proposal';
  id: string;
  tool: string;
  kind: ActionKind;
  target: Record<string, unknown>;
  summary: string;
  decision_required: boolean;
  delay_ms: number;
  step: number;
  total_steps: number;
  plan_goal?: string;
  security_reason?: string;
  undoable: boolean;
  expires_in: number;
  task_id?: string;
  _time?: string;
}

export interface ActionResolved {
  type: 'action_resolved';
  id: string;
  approved: boolean;
  auto: boolean;
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
  | PrivacyMasksChanged
  | TrustChanged
  | ActionProposal
  | ActionResolved
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
