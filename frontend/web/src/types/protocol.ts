/**
 * @fileoverview 前后端通信协议类型定义
 *
 * 与 src/illusion/ui/protocol.py 中的模型一一对应。
 * 定义了 Web 前端与后端之间通信所使用的所有数据类型。
 *
 * @module protocol
 */

// ---- 转录项 ----

/**
 * 转录项接口
 *
 * 表示对话中的一个消息项，可以是用户消息、助手回复、工具调用等。
 */
export interface TranscriptItem {
  /**
   * 消息角色类型：
   * - 'system': 系统消息
   * - 'user': 用户消息
   * - 'assistant': 助手回复
   * - 'tool': 工具调用
   * - 'tool_result': 工具执行结果
   * - 'log': 日志消息
   * - 'plan': 计划内容
   */
  role: 'system' | 'user' | 'assistant' | 'tool' | 'tool_result' | 'log' | 'plan';
  /** 消息文本内容 */
  text: string;
  /** 工具名称（仅在 role 为 'tool' 或 'tool_result' 时存在） */
  tool_name?: string;
  /** 工具输入参数（仅在 role 为 'tool' 时存在） */
  tool_input?: Record<string, unknown>;
  /** 是否为错误消息（仅在 role 为 'tool_result' 时存在） */
  is_error?: boolean;
  /** 助手的思考/推理过程（仅在 role 为 'assistant' 时存在） */
  reasoning?: string;
  /** 工具调用的唯一标识符（仅在 role 为 'tool' 或 'tool_result' 时存在） */
  tool_use_id?: string;
  /** 工具执行期间的流式进度消息（仅在 role 为 'tool_result' 时存在，
   *  由前端在 tool_completed 时从 pending 状态转移保留——agent 子任务的
   *  思考过程在完成后折叠展示，不随 pending 移除而丢失） */
  progress_messages?: Array<{message: string; type?: string}>;
}

// ---- 任务快照 ----

/**
 * 任务快照接口
 *
 * 表示后台任务的当前状态快照。
 */
export interface TaskSnapshot {
  /** 任务唯一标识符 */
  id: string;
  /** 任务类型 */
  type: string;
  /** 任务状态 */
  status: string;
  /** 任务描述 */
  description: string;
  /** 任务元数据 */
  metadata: Record<string, string>;
}

// ---- 选择 / 模态框 ----

/**
 * 选择选项接口
 *
 * 用于选择模态对话框中的单个选项。
 */
export interface SelectOption {
  /** 选项值（提交到后端的值） */
  value: string;
  /** 选项显示标签 */
  label: string;
  /** 选项描述（可选） */
  description?: string;
  /** 是否为当前活跃选项（可选） */
  active?: boolean;
}

/**
 * 选择请求载荷接口
 *
 * 后端发送到前端的选择请求，用于显示选择模态对话框。
 */
export interface SelectRequestPayload {
  /** 对话框标题 */
  title: string;
  /** 关联的命令名称 */
  command: string;
  /** 可选项列表 */
  options: SelectOption[];
}

/**
 * 待处理工具调用接口
 *
 * 表示一个已经开始但尚未完成的工具调用。
 */
export interface PendingToolCall {
  /** 工具名称 */
  tool_name: string;
  /** 工具调用的唯一标识符 */
  tool_use_id: string;
  /** 工具输入参数（可选） */
  tool_input?: Record<string, unknown>;
  /** 流式进度消息列表（可选，由 tool_progress 事件累积；message 为内容，type 为进度类型） */
  progressMessages?: Array<{message: string; type?: string}>;
}

/**
 * 待办事项快照接口
 *
 * 表示单个待办事项的当前状态。
 */
export interface TodoItemSnapshot {
  /** 待办事项内容 */
  content: string;
  /** 待办事项状态：'pending'（待处理）、'in_progress'（进行中）、'completed'（已完成） */
  status: string;
  /** 当前活动形式描述（如 "正在编写代码"） */
  activeForm: string;
}

/**
 * MCP 服务器快照接口
 *
 * 表示 MCP（Model Context Protocol）服务器的当前状态快照。
 */
export interface McpServerSnapshot {
  /** 服务器名称 */
  name: string;
  /** 服务器状态（如 'connected', 'disconnected' 等） */
  state: string;
  /** 状态详情（可选） */
  detail?: string;
  /** 传输协议类型（可选，如 'stdio', 'sse' 等） */
  transport?: string;
  /** 是否已配置认证（可选） */
  auth_configured?: boolean;
  /** 可用工具数量（可选） */
  tool_count?: number;
  /** 可用资源数量（可选） */
  resource_count?: number;
}

/**
 * 群体协作者快照接口
 *
 * 表示群体协作模式中的一个协作者的当前状态。
 */
export interface SwarmTeammateSnapshot {
  /** 协作者唯一标识符 */
  id: string;
  /** 协作者名称 */
  name: string;
  /** 协作者状态：'running'（运行中）、'idle'（空闲）、'done'（完成）、'error'（错误） */
  status: string;
}

/**
 * 群体协作通知快照接口
 *
 * 表示群体协作模式中的一个通知消息。
 */
export interface SwarmNotificationSnapshot {
  /** 通知消息内容 */
  message: string;
  /** 通知时间戳（Unix 时间戳，毫秒，可选） */
  timestamp?: number;
}

/**
 * 技能快照接口
 *
 * 表示一个可用的技能。
 */
export interface SkillSnapshot {
  /** 技能名称 */
  name: string;
  /** 技能描述 */
  description: string;
  /** 技能来源：'project'（项目级）、'user'（用户级）、'builtin'（内置） */
  source: string;
}

/**
 * 插件快照接口
 *
 * 表示一个已安装的插件。
 */
export interface PluginSnapshot {
  /** 插件名称 */
  name: string;
  /** 插件描述 */
  description: string;
  /** 是否已启用 */
  enabled: boolean;
  /** 技能数量 */
  skill_count: number;
  /** MCP 服务器数量 */
  mcp_count: number;
  /** 命令数量 */
  command_count: number;
}

/**
 * 规则快照接口
 *
 * 表示一个已加载的规则。
 */
export interface RuleSnapshot {
  /** 规则名称 */
  name: string;
  /** 规则来源：'project'（项目级）、'user'（用户级）、'builtin'（内置） */
  source: string;
}

// ---- 前端请求 ----

/**
 * 前端请求类型
 *
 * 前端发送到后端的所有可能请求类型。
 * web_* 类型为 Web 前端专属通道（A/B 通道），与 terminal 共用的
 * submit_line/apply_select_command 等类型隔离。
 */
export type FrontendRequest =
  | { type: 'submit_line'; line: string; treat_as_text?: boolean }
  | { type: 'stop' }
  | { type: 'permission_response'; request_id: string; allowed: boolean; always_allow?: boolean; tool_name?: string }
  | { type: 'question_response'; request_id: string; answer: string }
  | { type: 'list_sessions' }
  | { type: 'select_command'; command: string }
  | { type: 'apply_select_command'; command: string; value: string }
  | { type: 'shutdown' }
  // === Web 前端专属通道（web_* 命名空间）===
  | { type: 'web_new_session' }
  | { type: 'web_restore_session'; session_id: string }
  | { type: 'web_delete_sessions'; session_ids?: string[]; delete_all?: boolean }
  | { type: 'web_set_setting'; setting_key: string; setting_value: string | number | boolean }
  | { type: 'web_request_sessions'; limit?: number; offset?: number }
  | { type: 'web_request_models' }
  | { type: 'web_request_resources' }
  | { type: 'web_query'; command: string; args?: string; request_id: string }
  // === btw 侧问（terminal + web 共用）===
  | { type: 'btw_request'; question: string; request_id: string }
  | { type: 'btw_cancel'; request_id: string }
  // === agent 向导（terminal + web 共用）===
  | { type: 'agent_wizard_init' }
  | { type: 'agent_generate_request'; prompt: string; model: string; request_id: string }
  | { type: 'agent_generate_cancel'; request_id: string }
  | { type: 'agent_wizard_submit'; fields: Record<string, unknown>; scope: 'user' | 'project' };

// ---- 后端事件 ----

/**
 * 后端事件接口
 *
 * 后端通过 WebSocket 发送到前端的所有可能事件类型。
 * 不同类型的事件包含不同的载荷字段。
 */
export interface BackendEvent {
  /** 事件类型标识符 */
  type: string;
  /** 事件消息（可选） */
  message?: string;
  /** 转录项（可选） */
  item?: TranscriptItem;
  /** 转录项列表（可选，用于批量更新） */
  items?: TranscriptItem[];
  /** 状态信息（可选） */
  state?: Record<string, unknown>;
  /** 任务列表快照（可选） */
  tasks?: TaskSnapshot[];
  /** MCP 服务器列表快照（可选） */
  mcp_servers?: McpServerSnapshot[];
  /** 可用命令列表（可选） */
  commands?: string[];
  /** 模态对话框配置（可选） */
  modal?: Record<string, unknown> | null;
  /** 选择选项列表（可选） */
  select_options?: SelectOption[];
  /** 工具名称（可选） */
  tool_name?: string;
  /** 工具输入参数（可选） */
  tool_input?: Record<string, unknown>;
  /** 工具调用唯一标识符（可选） */
  tool_use_id?: string;
  /** 输出内容（可选） */
  output?: string;
  /** 是否为错误（可选） */
  is_error?: boolean;
  /** 工具数量（可选） */
  tool_count?: number;
  /** tool_progress 事件的进度类型（可选，如 'stdout'/'status'/'custom'） */
  progress_type?: string;
  /** 助手的思考/推理过程（可选） */
  reasoning?: string;
  /** 计划模式状态（可选） */
  plan_mode?: string;
  /** 待办事项列表快照（可选） */
  todo_items?: TodoItemSnapshot[];
  /** 待办事项 Markdown 文本（可选） */
  todo_markdown?: string;
  /** 群体协作者列表快照（可选） */
  swarm_teammates?: SwarmTeammateSnapshot[];
  /** 群体协作通知列表快照（可选） */
  swarm_notifications?: SwarmNotificationSnapshot[];
  /** 指令结果数据（可选） */
  command_result_data?: { message: string; type: 'success' | 'error' | 'info'; request_id?: string };
  // === web_* 推送事件字段 ===
  /** web_restore_started/completed 的会话 ID（可选） */
  session_id?: string;
  /** web_sessions 推送的会话列表（可选） */
  web_sessions?: WebSessionItem[];
  /** web_resources 推送的资源快照（可选） */
  web_resources?: {
    skills: SkillSnapshot[];
    plugins: PluginSnapshot[];
    rules: RuleSnapshot[];
    mcp_servers: McpServerSnapshot[];
  };
  /** web_models 推送的模型选项（可选） */
  web_models?: SelectOption[];
  /** web_setting_changed 的键名（可选） */
  setting_key?: string;
  /** web_setting_changed 的值（可选） */
  setting_value?: string | number | boolean;
  /** web_query_result 的结果类型（可选） */
  web_query_kind?: 'text' | 'transcript_replace' | 'download';
  /** web_query_result 的载荷（可选） */
  web_query_payload?: unknown;
  /** web_query_result 关联的请求 ID（可选） */
  web_request_id?: string;
  /** web_query_result 关联的命令名（可选） */
  web_command?: string;
  /** web_restore_completed 等事件的错误信息（非空表示操作失败）（可选） */
  web_error?: string;
  // === btw 侧问响应专属字段 ===
  /** btw_response 关联的请求 ID（可选） */
  request_id?: string;
  /** btw_response 的回复文本（可选，非 null 表示成功回复） */
  reply?: string | null;
  /** btw_response 的错误文本（可选，非空表示请求失败）（与布尔 is_error 区分） */
  error?: string | null;
  // === agent 向导响应专属字段 ===
  /** agent_wizard_init_response 推送的工具列表（可选） */
  tools?: { name: string; description: string }[];
  /** agent_wizard_init_response 推送的模型列表（可选，后端返回 name 字段） */
  models?: { name: string; label: string }[];
  /** agent_generate_response 返回的 LLM 生成草稿（可选） */
  agent?: { identifier: string; when_to_use: string; system_prompt: string };
  /** agent_wizard_result 的成功标志（可选） */
  success?: boolean;
  /** agent_wizard_result 的写入路径（可选，成功时返回） */
  path?: string;
  /** agent_wizard_result 的字段错误映射（可选，失败时返回字段级错误） */
  errors?: Record<string, string>;
  /** agent_wizard_submit 关联的表单字段（可选，回声） */
  fields?: Record<string, unknown>;
  /** agent_wizard_submit 关联的作用域（可选，回声） */
  scope?: string;
  /** agent_generate_request 关联的提示词（可选，回声） */
  prompt?: string;
}

/**
 * Web 会话项接口
 *
 * web_sessions 推送事件中的单个会话条目。
 */
export interface WebSessionItem {
  /** 会话唯一标识符 */
  id: string;
  /** 会话显示标签 */
  label: string;
  /** 创建时间戳（可选） */
  created_at?: number;
  /** 消息数量（可选） */
  message_count?: number;
  /** 会话摘要（可选） */
  summary?: string;
}

/**
 * 后端状态快照接口
 *
 * 对应后端 `_state_payload` 返回的字段（src/illusion/ui/protocol.py）。
 * 所有字段可选，因为前端可能收到部分更新或字段尚未到位。
 */
export interface StatusPayload {
  /** 当前模型名 */
  model?: string;
  /** 当前工作目录 */
  cwd?: string;
  /** 认证状态 */
  auth_status?: string;
  /** API base URL */
  base_url?: string;
  /** 权限模式 */
  permission_mode?: string;
  /** UI 语言 */
  ui_language?: string;
  /** 思考强度 */
  effort?: string;
  /** 已连接 MCP 服务器数 */
  mcp_connected?: number;
  /** 失败 MCP 服务器数 */
  mcp_failed?: number;
  /** 输出风格 */
  output_style?: string;
  /** 是否显示思考过程 */
  show_thinking?: boolean;
  /** 当前阶段 */
  phase?: string;
  /** 会话 ID */
  session_id?: string;
  /** 上下文窗口大小 */
  context_window?: number;
  /** 当前上下文已用 tokens（最后一次 API 真实值 + 新增消息估算） */
  context_tokens?: number;
  /** 最后一次 API 调用的缓存命中 tokens */
  context_cache_read?: number;
  /** 最后一次 API 调用的缓存写入 tokens */
  context_cache_creation?: number;
  /** 最后一次 API 调用的非缓存输入 tokens */
  context_input?: number;
  /** 最后一次 API 调用的输出 tokens */
  context_output?: number;
  /** 累积 API input tokens（非缓存） */
  input_tokens?: number;
  /** 累积 API output tokens */
  output_tokens?: number;
  /** 累积缓存命中 tokens */
  cache_read_input_tokens?: number;
  /** 累积缓存写入 tokens */
  cache_creation_input_tokens?: number;
  /** 最大 tokens */
  max_tokens?: number;
  /** 活动 agent 数 */
  agent_count?: number;
}
