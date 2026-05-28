/**
 * Web 前端国际化模块
 *
 * 支持 zh-CN 和 en 两种语言，语言由后端 settings 的 ui_language 字段决定
 */

export type UiLanguage = 'zh-CN' | 'en';

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
  settings: '设置',
  help: '帮助',
  back: '返回',
  build_anything: '构建任何东西',
  mode: '模式',
  model: '模型',
  effort: '思考强度',
  mode_default: '默认',
  mode_plan: '计划',
  mode_auto: '自动',
  effort_low: '低',
  effort_medium: '中',
  effort_high: '高',
  effort_xhigh: '超高',
  effort_max: '最大',
  sidebar_title: 'illusion code',
  resume_session: '恢复会话',
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
  settings: 'Settings',
  help: 'Help',
  back: 'Back',
  build_anything: 'Build anything',
  mode: 'Mode',
  model: 'Model',
  effort: 'Effort',
  mode_default: 'Default',
  mode_plan: 'Plan',
  mode_auto: 'Auto',
  effort_low: 'Low',
  effort_medium: 'Medium',
  effort_high: 'High',
  effort_xhigh: 'XHigh',
  effort_max: 'Max',
  sidebar_title: 'illusion code',
  resume_session: 'Resume Session',
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
};

export function t(lang: UiLanguage, key: string): string {
  if (lang === 'en') return EN[key] || ZH[key] || key;
  return ZH[key] || key;
}
