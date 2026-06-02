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
   */
  role: 'system' | 'user' | 'assistant' | 'tool' | 'tool_result' | 'log';
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
 * 桥接会话快照接口
 *
 * 表示桥接会话（Bridge Session）的当前状态快照。
 */
export interface BridgeSessionSnapshot {
  /** 会话唯一标识符 */
  session_id: string;
  /** 启动命令 */
  command: string;
  /** 工作目录 */
  cwd: string;
  /** 进程 ID（可选） */
  pid?: number;
  /** 会话状态 */
  status: string;
  /** 启动时间戳（Unix 时间戳，毫秒，可选） */
  started_at?: number;
  /** 输出文件路径（可选） */
  output_path?: string;
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
 */
export type FrontendRequest =
  | { type: 'submit_line'; line: string }
  | { type: 'stop' }
  | { type: 'permission_response'; request_id: string; allowed: boolean; always_allow?: boolean; tool_name?: string }
  | { type: 'question_response'; request_id: string; answer: string }
  | { type: 'list_sessions' }
  | { type: 'select_command'; command: string }
  | { type: 'apply_select_command'; command: string; value: string }
  | { type: 'shutdown' };

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
  /** 桥接会话列表快照（可选） */
  bridge_sessions?: BridgeSessionSnapshot[];
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
  command_result_data?: { message: string; type: 'success' | 'error' | 'info' };
}
