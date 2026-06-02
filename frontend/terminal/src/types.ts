/**
 * @fileoverview 类型定义模块
 *
 * 本模块定义了终端前端使用的所有 TypeScript 类型，包括：
 * - 前端配置类型
 * - 会话转录项类型
 * - 工具调用相关类型
 * - 后端事件类型
 * - 各种快照类型（任务、MCP 服务器、桥接会话等）
 *
 * @module types
 */

/**
 * 待处理的工具调用信息
 *
 * 表示一个已经开始但尚未收到参数的工具调用。
 */
export type PendingToolCall = {
	/** 工具名称 */
	tool_name: string;
	/** 工具调用的唯一标识符 */
	tool_use_id: string;
	/** 工具输入参数（可选，可能尚未到达） */
	tool_input?: Record<string, unknown>;
};

/**
 * 前端配置类型
 *
 * 从环境变量 ILLUSION_FRONTEND_CONFIG 中解析的配置对象。
 */
export type FrontendConfig = {
	/** 后端启动命令及其参数 */
	backend_command: string[];
	/** 初始提示词（可选），用于在会话开始时自动发送 */
	initial_prompt?: string | null;
};

/**
 * 会话转录项类型
 *
 * 表示对话中的一个消息项，可以是用户消息、助手回复、工具调用等。
 */
export type TranscriptItem = {
	/**
	 * 消息角色类型：
	 * - 'system': 系统消息
	 * - 'user': 用户消息
	 * - 'assistant': 助手回复
	 * - 'assistant_streaming': 助手流式回复（正在进行中）
	 * - 'tool': 工具调用
	 * - 'tool_result': 工具执行结果
	 * - 'log': 日志消息
	 * - 'plan': 计划内容
	 */
	role: 'system' | 'user' | 'assistant' | 'assistant_streaming' | 'tool' | 'tool_result' | 'log' | 'plan';
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
};

/**
 * 任务快照类型
 *
 * 表示后台任务的当前状态快照。
 */
export type TaskSnapshot = {
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
};

/**
 * MCP 服务器快照类型
 *
 * 表示 MCP（Model Context Protocol）服务器的当前状态快照。
 */
export type McpServerSnapshot = {
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
};

/**
 * 桥接会话快照类型
 *
 * 表示桥接会话（Bridge Session）的当前状态快照。
 * 桥接会话用于管理与外部进程的通信。
 */
export type BridgeSessionSnapshot = {
	/** 会话唯一标识符 */
	session_id: string;
	/** 启动命令 */
	command: string;
	/** 工作目录 */
	cwd: string;
	/** 进程 ID */
	pid: number;
	/** 会话状态 */
	status: string;
	/** 启动时间戳（Unix 时间戳，毫秒） */
	started_at: number;
	/** 输出文件路径 */
	output_path: string;
};

/**
 * 选择选项载荷类型
 *
 * 用于选择模态对话框中的单个选项。
 */
export type SelectOptionPayload = {
	/** 选项值（提交到后端的值） */
	value: string;
	/** 选项显示标签 */
	label: string;
	/** 选项描述（可选） */
	description?: string;
	/** 是否为当前活跃选项（可选） */
	active?: boolean;
};

/**
 * 选择请求载荷类型
 *
 * 后端发送到前端的选择请求，用于显示选择模态对话框。
 */
export type SelectRequestPayload = {
	/** 对话框标题 */
	title: string;
	/** 关联的命令名称 */
	command: string;
	/** 可选项列表 */
	options: SelectOptionPayload[];
};

/**
 * 待办事项快照类型
 *
 * 表示单个待办事项的当前状态。
 */
export type TodoItemSnapshot = {
	/** 待办事项内容 */
	content: string;
	/** 待办事项状态：'pending'（待处理）、'in_progress'（进行中）、'completed'（已完成） */
	status: 'pending' | 'in_progress' | 'completed';
	/** 当前活动形式描述（如 "正在编写代码"） */
	activeForm: string;
};

/**
 * 群体协作者快照类型
 *
 * 表示群体协作模式中的一个协作者（teammate）的当前状态。
 */
export type SwarmTeammateSnapshot = {
	/** 协作者名称 */
	name: string;
	/** 协作者状态：'running'（运行中）、'idle'（空闲）、'done'（已完成）、'error'（错误） */
	status: 'running' | 'idle' | 'done' | 'error';
	/** 运行时长（秒，可选） */
	duration?: number;
	/** 当前任务描述（可选） */
	task?: string;
};

/**
 * 群体协作通知快照类型
 *
 * 表示群体协作模式中的一个通知消息。
 */
export type SwarmNotificationSnapshot = {
	/** 发送者名称 */
	from: string;
	/** 通知消息内容 */
	message: string;
	/** 通知时间戳（Unix 时间戳，毫秒） */
	timestamp: number;
};

/**
 * 后端事件类型
 *
 * 后端通过 WebSocket 发送到前端的所有可能事件类型。
 * 不同类型的事件包含不同的载荷字段。
 */
export type BackendEvent = {
	/** 事件类型标识符 */
	type: string;
	/** 事件消息（可选） */
	message?: string | null;
	/** 转录项（可选） */
	item?: TranscriptItem | null;
	/** 状态信息（可选） */
	state?: Record<string, unknown> | null;
	/** 任务列表快照（可选） */
	tasks?: TaskSnapshot[] | null;
	/** MCP 服务器列表快照（可选） */
	mcp_servers?: McpServerSnapshot[] | null;
	/** 桥接会话列表快照（可选） */
	bridge_sessions?: BridgeSessionSnapshot[] | null;
	/** 可用命令列表（可选） */
	commands?: string[] | null;
	/** 模态对话框配置（可选） */
	modal?: Record<string, unknown> | null;
	/** 选择选项列表（可选） */
	select_options?: SelectOptionPayload[] | null;
	/** 工具名称（可选） */
	tool_name?: string | null;
	/** 工具输入参数（可选） */
	tool_input?: Record<string, unknown> | null;
	/** 工具调用唯一标识符（可选） */
	tool_use_id?: string | null;
	/** 输出内容（可选） */
	output?: string | null;
	/** 是否为错误（可选） */
	is_error?: boolean | null;
	// 新事件载荷
	/** 待办事项列表快照（可选） */
	todo_items?: TodoItemSnapshot[] | null;
	/** 待办事项 Markdown 文本（可选） */
	todo_markdown?: string | null;
	/** 计划模式状态（可选） */
	plan_mode?: string | null;
	/** 群体协作者列表快照（可选） */
	swarm_teammates?: SwarmTeammateSnapshot[] | null;
	/** 群体协作通知列表快照（可选） */
	swarm_notifications?: SwarmNotificationSnapshot[] | null;
	/** 助手的思考/推理过程（可选） */
	reasoning?: string | null;
	/** 指令结果数据（可选） */
	command_result_data?: {
		/** 结果消息 */
		message: string;
		/** 结果类型：'success'（成功）、'error'（错误）、'info'（信息） */
		type: 'success' | 'error' | 'info';
	} | null;
	/** 转录项列表（可选，用于批量更新） */
	items?: TranscriptItem[] | null;
};
