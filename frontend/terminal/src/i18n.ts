/**
 * @fileoverview 国际化（i18n）模块
 *
 * 本模块提供终端前端的多语言支持功能，目前支持：
 * - 简体中文（zh-CN）
 * - 英文（en）
 *
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
 * 语言字典类型
 * 键为文本标识符，值为对应语言的翻译文本
 */
type Dict = Record<string, string>;

/**
 * 简体中文字典
 * 包含所有 UI 文本的中文翻译
 */
const ZH: Dict = {
	connecting: '正在连接后端...',
	send: '发送',
	commands: '命令',
	exit: '退出',
	exitProgram: '退出程序',
	stopCurrentTask: '停止当前任务',
	permissionMode: '权限模式',
	language: '语言',
	langZh: '简体中文',
	langEn: 'English',
	newline: '换行',
	allow: '允许',
	alwaysAllow: '总是允许',
	deny: '拒绝',
	welcomeSub: 'AI 编码助手',
	statusReady: '就绪',
	statusThinking: '思考中...',
	statusExecuting: '执行指令中...',
	statusToolPrefix: '执行工具',
	spinnerVerbs: '酝酿,生发,铺陈,点染,贯通,渲染,独照,澄明',
	spinnerToolAction: '正在执行',
	longTextHint: '多段需求或长文本建议写入文档后命 illusion code 读取',
	clearInput: '清空输入',
	taskStopped: '当前任务已停止。',
	reasoning: '思考过程',
	assistantReply: '助手回复',
	bgAgentWaiting: '等待后台代理完成',
	bgAgentResuming: '后台代理已完成，继续执行',
	planReview: '计划审批',
	approve: '批准',
	reject: '拒绝',
	planApproved: '计划已批准，开始实施。',
	planRejected: '计划已拒绝。',
	planFeedbackPrompt: '请输入修改意见（可选，Enter 提交，Esc 跳过）：',
	// ---- ask_user_question 问答模态框文案 ----
	questionOther: '其他',
	questionOtherPlaceholder: '请输入...',
	questionSelectOne: '选择一项',
	questionSelectAll: '选择所有适用项',
	questionSubmit: '提交',
	questionNext: '下一题',
	questionReviewTitle: '复核你的答案',
	questionNotAllAnswered: '还有问题未作答',
	questionReadyToSubmit: '准备好提交答案了吗？',
	questionNoAnswer: '（未作答）',
	// ---- 底部辅助行片段（每个片段单独 i18n，动态拼接）----
	questionHintSelect: '选择',
	questionHintNavigate: '上下导航',
	questionHintSwitchTab: 'Tab/方向键切换问题',
	questionHintToggle: 'Space 切换',
	questionHintSubmit: 'Enter 提交',
	questionHintCancel: 'Esc 取消',
	questionHintNotes: 'n 添加备注',
	questionHintQuickSelect: '数字键快捷选择',
};

/**
 * 英文字典
 * 包含所有 UI 文本的英文翻译
 */
const EN: Dict = {
	connecting: 'Connecting to backend...',
	send: 'send',
	commands: 'commands',
	exit: 'exit',
	exitProgram: 'exit program',
	stopCurrentTask: 'stop current task',
	permissionMode: 'Permission Mode',
	language: 'Language',
	langZh: '简体中文',
	langEn: 'English',
	newline: 'newline',
	allow: 'Allow',
	alwaysAllow: 'Always Allow',
	deny: 'Deny',
	welcomeSub: 'An AI-powered coding assistant',
	statusReady: 'Ready',
	statusThinking: 'Thinking...',
	statusExecuting: 'Executing command...',
	statusToolPrefix: 'Running tool',
	spinnerVerbs: 'Thinking,Processing,Analyzing,Reasoning,Generating,Deliberating,Crafting,Refining,Computing,Synthesizing',
	spinnerToolAction: 'Running',
	longTextHint: 'For complex or long text, write to doc and let illusion code read it',
	clearInput: 'clear input',
	taskStopped: 'Current task stopped.',
	reasoning: 'Thinking',
	assistantReply: 'Response',
	bgAgentWaiting: 'Waiting for background agent',
	bgAgentResuming: 'Background agent completed, resuming',
	planReview: 'Plan Review',
	approve: 'Approve',
	reject: 'Reject',
	planApproved: 'Plan approved. Starting implementation.',
	planRejected: 'Plan rejected.',
	planFeedbackPrompt: 'Enter feedback (optional, Enter to submit, Esc to skip): ',
	// ---- ask_user_question question modal strings ----
	questionOther: 'Other',
	questionOtherPlaceholder: 'Type something...',
	questionSelectOne: 'Select one',
	questionSelectAll: 'Select all that apply',
	questionSubmit: 'Submit',
	questionNext: 'Next',
	questionReviewTitle: 'Review your answers',
	questionNotAllAnswered: 'You have not answered all questions',
	questionReadyToSubmit: 'Ready to submit your answers?',
	questionNoAnswer: '(No answer)',
	// ---- bottom hint line fragments (each fragment is i18n'd, composed dynamically) ----
	questionHintSelect: 'select',
	questionHintNavigate: '↑/↓ to navigate',
	questionHintSwitchTab: 'Tab/Arrows to switch questions',
	questionHintToggle: 'Space to toggle',
	questionHintSubmit: 'Enter to submit',
	questionHintCancel: 'Esc to cancel',
	questionHintNotes: 'n to add notes',
	questionHintQuickSelect: '1-N quick select',
};

/**
 * 所有语言字典的集合
 * 按语言代码索引对应的翻译字典
 */
const ALL: Record<UiLanguage, Dict> = {
	'zh-CN': ZH,
	en: EN,
};

/**
 * 标准化语言代码
 *
 * 将输入的语言值标准化为有效的 UiLanguage 类型。
 * 如果输入为 'en' 则返回 'en'，否则默认返回 'zh-CN'。
 *
 * @param raw - 原始语言值（可能为任意类型）
 * @returns 标准化后的语言代码
 */
export function normalizeLanguage(raw: unknown): UiLanguage {
	return raw === 'en' ? 'en' : 'zh-CN';
}

/**
 * 获取国际化文本
 *
 * 根据当前语言和文本键获取对应的翻译文本。
 * 如果指定语言中不存在该键，则回退到中文文本。
 *
 * @param lang - 当前 UI 语言
 * @param key - 文本标识符（必须是中文字典中已定义的键）
 * @returns 对应语言的翻译文本
 */
export function t(lang: UiLanguage, key: keyof typeof ZH): string {
	return ALL[lang][key] ?? ZH[key];
}
