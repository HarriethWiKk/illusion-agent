/**
 * @fileoverview 工具名 → 友好显示名映射
 *
 * Web 端从后端收到的 tool_name 是 snake_case（如 `todo_write`、`task_create`），
 * 直接显示不美观。本模块对照 terminal 端 tools/registry.ts 的 displayName
 * 定义，提供统一的映射表，未命中的工具名回退为 PascalCase 转换结果。
 *
 * @module utils/toolDisplayName
 */

/**
 * 已知工具名 → 显示名映射表
 * 对照 frontend/terminal/src/tools/registry.ts 中各工具的 displayName
 */
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  // Shell 类
  bash: 'Bash',
  powershell: 'PowerShell',

  // 文件类
  read_file: 'Read',
  read: 'Read',
  fileread: 'Read',
  write_file: 'Write',
  write: 'Write',
  filewrite: 'Write',
  edit_file: 'Update',
  edit: 'Update',
  fileedit: 'Update',

  // 搜索类
  grep: 'Search',
  glob: 'Search',

  // 子代理
  agent: 'Agent',

  // Web 类
  web_search: 'Web Search',
  web_fetch: 'Fetch',

  // LSP / Notebook / Skill
  lsp: 'LSP',
  notebook_edit: 'Edit Notebook',
  skill: 'Skill',

  // 任务管理类
  task_create: 'TaskCreate',
  task_update: 'TaskUpdate',
  task_get: 'TaskGet',
  task_list: 'TaskList',
  task_output: 'Task Output',
  task_stop: 'Stop Task',

  // Todo
  todo_write: 'TodoWrite',
  TodoWrite: 'TodoWrite',

  // 计划模式
  enter_plan_mode: 'EnterPlanMode',
  exit_plan_mode: 'ExitPlanMode',

  // 工作树
  enter_worktree: 'EnterWorktree',
  exit_worktree: 'ExitWorktree',

  // Cron / Config / ToolSearch
  cron: 'Cron',
  config: 'Config',
  tool_search: 'ToolSearch',

  // MCP
  mcp: 'mcp',
  list_mcp_resources: 'listMcpResources',
  read_mcp_resource: 'readMcpResource',

  // 通用工具
  ask_user_question: 'AskUserQuestion',
  sleep: 'Sleep',
  repl: 'REPL',
  send_message: 'SendMessage',
  team_create: 'TeamCreate',
  team_delete: 'TeamDelete',
  mcp_auth: 'McpAuth',
  structured_output: 'StructuredOutput',

  // 渠道媒体工具（当前渠道内发/收文件）
  send_media: 'SendMedia',
  receive_media: 'ReceiveMedia',
  // 跨渠道文件传输
  list_channel_sessions: 'ListChannelSessions',
  send_to_channel: 'SendToChannel',
  // 飞书文档工具
  feishu_doc_read: 'FeishuDocRead',
  feishu_doc_create: 'FeishuDocCreate',
  feishu_doc_write: 'FeishuDocWrite',
  feishu_doc_delete: 'FeishuDocDelete',
  // 飞书云盘工具
  feishu_drive_list: 'FeishuDriveList',
  feishu_drive_upload: 'FeishuDriveUpload',
  feishu_drive_download: 'FeishuDriveDownload',
  feishu_drive_mkdir: 'FeishuDriveMkdir',
  feishu_drive_delete: 'FeishuDriveDelete',

  // 权限/计划相关（后端事件名）
  set_permission_mode: 'SetPermissionMode',
  plan_mode: 'PlanMode',
};

/**
 * 将 snake_case 工具名转为 PascalCase 作为回退显示名
 * 例如 `task_create` → `TaskCreate`，`web_search` → `WebSearch`
 */
function toPascalCase(snake: string): string {
  return snake
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('');
}

/**
 * 获取工具的友好显示名
 *
 * 查找顺序：
 *   1. 精确匹配映射表
 *   2. snake_case → PascalCase 转换
 *   3. 原名回退
 *
 * @param toolName 后端发送的工具名（snake_case 或 PascalCase）
 * @returns 友好显示名
 */
export function toolDisplayName(toolName: string | undefined | null): string {
  if (!toolName) return '';
  const exact = TOOL_DISPLAY_NAMES[toolName];
  if (exact) return exact;
  // 已是 PascalCase/camelCase（无下划线）则原样返回
  if (!toolName.includes('_')) return toolName;
  return toPascalCase(toolName);
}
