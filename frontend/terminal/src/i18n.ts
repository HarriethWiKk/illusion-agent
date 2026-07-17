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
	connecting: '正在抵达云端...',
	exitProgram: '退出',
	stopCurrentTask: '停止',
	permissionMode: '权限模式',
	permDefaultDesc: '写入或执行前询问',
	permAutoDesc: '自动允许所有工具',
	permPlanDesc: '阻止所有写入操作',
	language: '语言',
	langZh: '简体中文',
	langEn: 'English',
	newline: '换行',
	allow: '允许',
	alwaysAllow: '总是允许',
	deny: '拒绝',
	spinnerVerbs: '酝酿,生发,铺陈,点染,贯通,渲染,推敲,沉吟,斟酌,打磨,勾勒,描摹',
	spinnerToolAction: '正在着手',
	longTextHint: '尽情输入吧，多行、粘贴代码都不在话下，输入 "/" 开启更多玩法',
	clearInput: '删行',
	lineStart: '行首',
	lineEnd: '行尾',
	taskStopped: '当前任务已停止。',
	reasoning: '思考过程',
	assistantReply: '助手回复',
	planReview: '计划审批',
	approve: '批准',
	reject: '拒绝',
	// ---- ask_user_question 问答模态框文案 ----
	questionOther: '其他',
	questionOtherPlaceholder: '请输入...',
	questionSelectOne: '选择一项',
	questionSelectAll: '选择所有适用项',
	questionSubmit: '提交',
	questionReviewTitle: '确认你的选择',
	questionNotAllAnswered: '还有问题未作答',
	questionReadyToSubmit: '准备好提交了吗？',
	questionNoAnswer: '（未作答）',
	// ---- 底部辅助行片段（每个片段单独 i18n，动态拼接）----
	questionHintSelect: '选择',
	questionHintNavigate: '上下导航',
	questionHintSwitchTab: 'Tab/方向键切换问题',
	questionHintToggle: 'Space 切换',
	questionHintSubmit: 'Enter 提交',
	questionHintCancel: 'Esc 取消',
	questionHintQuickSelect: '数字键快捷选择',
	// ---- 后端退出兜底提示 ----
	backend_exit_hint: '后端启动失败。请运行 \'illusion auth login\' 配置 API 环境，或检查 settings.json 配置。',
};

/**
 * 英文字典
 * 包含所有 UI 文本的英文翻译
 */
const EN: Dict = {
	connecting: 'Ascending to the cloud...',
	exitProgram: 'exit',
	stopCurrentTask: 'stop',
	permissionMode: 'Permission Mode',
	permDefaultDesc: 'Ask before write/execute operations',
	permAutoDesc: 'Allow all tools automatically',
	permPlanDesc: 'Block all write operations',
	language: 'Language',
	langZh: '简体中文',
	langEn: 'English',
	newline: 'newline',
	allow: 'Allow',
	alwaysAllow: 'Always Allow',
	deny: 'Deny',
	spinnerVerbs: 'Thinking,Processing,Analyzing,Reasoning,Generating,Deliberating,Crafting,Refining,Computing,Synthesizing',
	spinnerToolAction: 'Wielding tool',
	longTextHint: 'Type away — multi-line & code paste all work! Type "/" for more possibilities',
	clearInput: 'delete line',
	lineStart: 'start',
	lineEnd: 'end',
	taskStopped: 'Current task stopped.',
	reasoning: 'Thinking',
	assistantReply: 'Response',
	planReview: 'Plan Review',
	approve: 'Approve',
	reject: 'Reject',
	// ---- ask_user_question question modal strings ----
	questionOther: 'Other',
	questionOtherPlaceholder: 'Type something...',
	questionSelectOne: 'Select one',
	questionSelectAll: 'Select all that apply',
	questionSubmit: 'Submit',
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
	questionHintQuickSelect: '1-N quick select',
	// ---- backend exit fallback hint ----
	backend_exit_hint: 'Backend startup failed. Run \'illusion auth login\' to configure API environment, or check settings.json.',
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
