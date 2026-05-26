export type UiLanguage = 'zh-CN' | 'en';

type Dict = Record<string, string>;

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
};

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
};

const ALL: Record<UiLanguage, Dict> = {
	'zh-CN': ZH,
	en: EN,
};

export function normalizeLanguage(raw: unknown): UiLanguage {
	return raw === 'en' ? 'en' : 'zh-CN';
}

export function t(lang: UiLanguage, key: keyof typeof ZH): string {
	return ALL[lang][key] ?? ZH[key];
}
