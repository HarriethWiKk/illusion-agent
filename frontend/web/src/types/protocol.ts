/**
 * 前后端通信协议类型定义
 *
 * 与 src/illusion/ui/protocol.py 中的模型一一对应
 */

// ---- Transcript Item ----

export interface TranscriptItem {
  role: 'system' | 'user' | 'assistant' | 'tool' | 'tool_result' | 'log';
  text: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  is_error?: boolean;
  reasoning?: string;
  tool_use_id?: string;
}

// ---- Task Snapshot ----

export interface TaskSnapshot {
  id: string;
  type: string;
  status: string;
  description: string;
  metadata: Record<string, string>;
}

// ---- Select / Modal ----

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
  active?: boolean;
}

export interface SelectRequestPayload {
  title: string;
  command: string;
  options: SelectOption[];
}

export interface PendingToolCall {
  tool_name: string;
  tool_use_id: string;
  tool_input?: Record<string, unknown>;
}

export interface TodoItemSnapshot {
  content: string;
  status: string;
  activeForm: string;
}

export interface McpServerSnapshot {
  name: string;
  state: string;
  detail?: string;
  transport?: string;
  auth_configured?: boolean;
  tool_count?: number;
  resource_count?: number;
}

export interface BridgeSessionSnapshot {
  session_id: string;
  command: string;
  cwd: string;
  pid?: number;
  status: string;
  started_at?: number;
  output_path?: string;
}

export interface SwarmTeammateSnapshot {
  id: string;
  name: string;
  status: string;
}

export interface SwarmNotificationSnapshot {
  message: string;
  timestamp?: number;
}

// ---- Frontend Request ----

export type FrontendRequest =
  | { type: 'submit_line'; line: string }
  | { type: 'stop' }
  | { type: 'permission_response'; request_id: string; allowed: boolean; always_allow?: boolean; tool_name?: string }
  | { type: 'question_response'; request_id: string; answer: string }
  | { type: 'list_sessions' }
  | { type: 'select_command'; command: string }
  | { type: 'apply_select_command'; command: string; value: string }
  | { type: 'shutdown' };

// ---- Backend Event ----

export interface BackendEvent {
  type: string;
  message?: string;
  item?: TranscriptItem;
  items?: TranscriptItem[];
  state?: Record<string, unknown>;
  tasks?: TaskSnapshot[];
  mcp_servers?: McpServerSnapshot[];
  bridge_sessions?: BridgeSessionSnapshot[];
  commands?: string[];
  modal?: Record<string, unknown> | null;
  select_options?: SelectOption[];
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_use_id?: string;
  output?: string;
  is_error?: boolean;
  tool_count?: number;
  reasoning?: string;
  plan_mode?: string;
  todo_items?: TodoItemSnapshot[];
  todo_markdown?: string;
  swarm_teammates?: SwarmTeammateSnapshot[];
  swarm_notifications?: SwarmNotificationSnapshot[];
  command_result_data?: { message: string; type: 'success' | 'error' | 'info' };
}
