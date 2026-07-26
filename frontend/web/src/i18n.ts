/**
 * @fileoverview Web 前端国际化模块
 *
 * 支持 zh-CN 和 en 两种语言，语言由后端 settings 的 ui_language 字段决定。
 * 所有用户可见的文本都应通过 t() 函数获取，以确保语言切换功能正常工作。
 *
 * @module i18n
 */

/**
 * 支持的 UI 语言类型
 * - 'zh-CN': 简体中文
 * - 'en': 英文
 */
export type UiLanguage = 'zh-CN' | 'en';

/**
 * 标准化语言代码
 *
 * 将输入的语言值标准化为有效的 UiLanguage 类型。
 * 如果输入为以 'en' 开头的字符串则返回 'en'，否则默认返回 'zh-CN'。
 *
 * @param raw - 原始语言值（可能为任意类型）
 * @returns 标准化后的语言代码
 */
export function normalizeLanguage(raw: unknown): UiLanguage {
  if (typeof raw === 'string' && raw.toLowerCase().startsWith('en')) return 'en';
  return 'zh-CN';
}

const ZH: Record<string, string> = {
  welcome: '欢迎使用 Illusion Code',
  thinking: '思考中...',
  tool_using: '正在使用工具...',
  error_occurred: '发生错误',
  task_stopped: '任务已停止',
  no_active_task: '没有活动任务',
  session_busy: '会话忙，请稍候',
  press_enter: '按 Enter 发送，Shift+Enter 换行',
  input_placeholder: '随便问点什么…',
  send: '发送',
  new_session: '新建会话',
  load_more: '加载更多',
  restoring_session: '正在恢复会话…',
  restore_failed: '恢复会话失败',
  settings: '设置',
  help: '帮助',
  back: '返回',
  build_anything: '构建任何东西',
  mode: '模式',
  model: '模型',
  effort: '思考强度',
  mode_default: '默认',
  mode_plan: '计划',
  planReview: '计划审批',
  mode_auto: '自动',
  effort_low: '低',
  effort_medium: '中',
  effort_high: '高',
  effort_xhigh: '超高',
  effort_max: '最大',
  effort_default: '默认',
  sidebar_title: 'illusion code',
  management_title: 'management',
  no_todos: '暂无待办',
  toggle_theme: '切换深色/浅色主题',
  theme_light: '浅色',
  theme_dark: '深色',
  resume_session: '会话列表',
  delete_session: '删除会话',
  language: '语言',
  current: '当前',
  permission_request: '权限请求',
  allow: '允许',
  deny: '拒绝',
  always_allow: '总是允许',
  cancel: '取消',
  connecting: '正在连接...',
  disconnected: '连接已断开',
  reconnecting: '正在重连...',
  thinking_process: '思考过程',
  confirm_delete: '确认删除',
  confirm_delete_session: '确定要删除此会话吗？此操作不可撤销。',
  delete_all: '清除所有',
  no_sessions: '没有可删除的会话',
  status_panel: '状态',
  session_info: '会话',
  context_usage: '上下文',
  cwd: '工作目录',
  connected_status: '连接状态',
  permission: '权限',
  thinking_level: '思考强度',
  tokens: 'tokens',
  collapse_panel: '收起侧栏',
  expand_panel: '展开侧栏',
  context_window: '上下文窗口',
  question_submit: '提交',
  question_placeholder: '输入你的回答...',
  multi_select_confirm: '确认',
  copy: '复制',
  copied: '已复制',
  rewind: '撤销',
  scroll_to_bottom: '回到底部',
  show_earlier: '显示 {count} 条更早对话',
  collapse_messages: '收起',
  thinking_process_count: '思考过程（{count} 步）',
  rewind_confirm_title: '选择回退范围',
  rewind_code: '回退代码',
  rewind_conversation: '回退对话',
  rewind_both: '回退代码与对话',
  rewind_code_desc: '仅撤销文件变更',
  rewind_conversation_desc: '仅删除对话记录',
  rewind_both_desc: '同时回退代码和对话',
  regenerate: '重新生成',
  collapse_session_list: '收起会话列表',
  expand_session_list: '展开会话列表',
};

const EN: Record<string, string> = {
  welcome: 'Welcome to Illusion Code',
  thinking: 'Thinking...',
  tool_using: 'Using tools...',
  error_occurred: 'An error occurred',
  task_stopped: 'Task stopped',
  no_active_task: 'No active task',
  session_busy: 'Session busy, please wait',
  press_enter: 'Press Enter to send, Shift+Enter for new line',
  input_placeholder: 'Ask anything...',
  send: 'Send',
  new_session: 'New Session',
  load_more: 'Load more',
  restoring_session: 'Restoring session…',
  restore_failed: 'Failed to restore session',
  settings: 'Settings',
  help: 'Help',
  back: 'Back',
  build_anything: 'Build anything',
  mode: 'Mode',
  model: 'Model',
  effort: 'Effort',
  mode_default: 'Default',
  mode_plan: 'Plan',
  planReview: 'Plan Review',
  mode_auto: 'Auto',
  effort_low: 'Low',
  effort_medium: 'Medium',
  effort_high: 'High',
  effort_xhigh: 'XHigh',
  effort_max: 'Max',
  effort_default: 'Default',
  sidebar_title: 'illusion code',
  management_title: 'management',
  no_todos: 'No todos',
  toggle_theme: 'Toggle dark/light theme',
  theme_light: 'Light',
  theme_dark: 'Dark',
  resume_session: 'Sessions',
  delete_session: 'Delete Session',
  language: 'Language',
  current: 'Current',
  permission_request: 'Permission Request',
  allow: 'Allow',
  deny: 'Deny',
  always_allow: 'Always Allow',
  cancel: 'Cancel',
  connecting: 'Connecting...',
  disconnected: 'Disconnected',
  reconnecting: 'Reconnecting...',
  thinking_process: 'Thinking',
  confirm_delete: 'Confirm Delete',
  confirm_delete_session: 'Are you sure you want to delete this session? This cannot be undone.',
  delete_all: 'Delete All',
  no_sessions: 'No sessions to delete',
  status_panel: 'Status',
  session_info: 'Session',
  context_usage: 'Context',
  cwd: 'Working Dir',
  connected_status: 'Connection',
  permission: 'Permission',
  thinking_level: 'Thinking',
  tokens: 'tokens',
  collapse_panel: 'Collapse',
  expand_panel: 'Expand',
  context_window: 'Context Window',
  question_submit: 'Submit',
  question_placeholder: 'Type your answer...',
  multi_select_confirm: 'Confirm',
  copy: 'Copy',
  copied: 'Copied',
  rewind: 'Rewind',
  scroll_to_bottom: 'Scroll to bottom',
  show_earlier: 'Show {count} earlier messages',
  collapse_messages: 'Collapse',
  thinking_process_count: 'Thinking ({count} steps)',
  rewind_confirm_title: 'Select Rewind Scope',
  rewind_code: 'Rewind Code',
  rewind_conversation: 'Rewind Conversation',
  rewind_both: 'Rewind Both',
  rewind_code_desc: 'Undo file changes only',
  rewind_conversation_desc: 'Delete conversation only',
  rewind_both_desc: 'Rewind both code and conversation',
  regenerate: 'Regenerate',
  collapse_session_list: 'Collapse session list',
  expand_session_list: 'Expand session list',
};

/**
 * 获取国际化文本
 *
 * 根据当前语言和文本键获取对应的翻译文本。
 * 如果指定语言中不存在该键，则回退到中文文本。
 * 如果中文中也不存在，则返回键名本身。
 *
 * @param lang - 当前 UI 语言
 * @param key - 文本标识符
 * @returns 对应语言的翻译文本
 */
export function t(lang: UiLanguage, key: string): string {
  if (lang === 'en') return EN[key] || ZH[key] || key;
  return ZH[key] || key;
}
