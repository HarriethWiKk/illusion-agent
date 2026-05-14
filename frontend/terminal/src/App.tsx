import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp, useInput} from 'ink';

import {CommandPicker} from './components/CommandPicker.js';
import {ConversationView} from './components/ConversationView.js';
import {ModalHost} from './components/ModalHost.js';
import {PromptInput} from './components/PromptInput.js';
import {SelectModal, type SelectOption} from './components/SelectModal.js';
import {Spinner} from './components/Spinner.js';
import {StatusBar} from './components/StatusBar.js';
import {SwarmPanel} from './components/SwarmPanel.js';
import {TodoPanel} from './components/TodoPanel.js';
import {useBackendSession} from './hooks/useBackendSession.js';
import {normalizeLanguage, t} from './i18n.js';
import {ThemeProvider, useTheme} from './theme/ThemeContext.js';
import type {FrontendConfig} from './types.js';

const rawReturnSubmit = process.env.ILLUSION_FRONTEND_RAW_RETURN === '1';
const scriptedSteps = (() => {
	const raw = process.env.ILLUSION_FRONTEND_SCRIPT;
	if (!raw) {
		return [] as string[];
	}
	try {
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : [];
	} catch {
		return [];
	}
})();

const PERMISSION_MODES: SelectOption[] = [
	{value: 'default', label: 'Default', description: 'Ask before write/execute operations'},
	{value: 'full_auto', label: 'Auto', description: 'Allow all tools automatically'},
	{value: 'plan', label: 'Plan Mode', description: 'Block all write operations'},
];

type SelectModalState = {
	title: string;
	options: SelectOption[];
	onSelect: (value: string) => void;
} | null;

const PERMISSION_PROMPT_OPTIONS: SelectOption[] = [
	{value: 'allow', label: 'Allow', description: 'Approve this tool execution'},
	{value: 'always', label: 'Always Allow', description: 'Always allow this tool without asking again'},
	{value: 'deny', label: 'Deny', description: 'Reject this tool execution'},
];

/** 命令描述映射表（中文） */
const COMMAND_DESC_ZH: Record<string, string> = {
	help: '显示可用命令',
	exit: '退出 IllusionCode',
	clear: '清空当前对话历史',
	new: '开启新对话并重置任务 ID',
	version: '显示已安装版本',
	status: '显示会话状态',
	context: '显示系统提示词或管理上下文窗口',
	summary: '总结对话历史',
	compact: '压缩较早对话历史',
	cost: '显示 token 用量和预估费用',
	usage: '显示用量与 token 估算',
	stats: '显示会话统计',
	memory: '查看和管理项目记忆',
	hooks: '显示已配置 hooks',
	resume: '恢复最近保存的会话',
	export: '导出当前转录',
	share: '创建可分享的转录快照',
	copy: '复制最新回复或指定文本',
	rewind: '移除最新对话轮次',
	files: '列出当前工作区文件',
	init: '初始化项目 IllusionCode 文件',
	bridge: '查看 bridge 辅助信息并创建 bridge 会话',
	login: '查看认证状态或保存 API Key',
	logout: '清除已保存 API Key',
	feedback: '保存 CLI 反馈到本地日志',
	skills: '列出或显示可用技能',
	config: '显示或更新配置',
	mcp: '显示 MCP 状态',
	plugin: '管理插件',
	'reload-plugins': '重新加载当前工作区插件发现结果',
	permissions: '显示或更新权限模式',
	plan: '切换计划权限模式',
	fast: '显示或更新快速模式',
	effort: '显示或更新推理强度',
	passes: '显示或更新推理轮数',
	turns: '显示或更新最大 agent 轮数',
	continue: '在中断后继续上一轮工具循环',
	model: '显示或更新默认模型',
	language: '显示或更新界面语言',
	'output-style': '显示或更新输出风格',
	doctor: '显示环境诊断信息',
	diff: '显示 git diff 输出',
	branch: '显示 git 分支信息',
	commit: '显示状态或创建 git 提交',
	issue: '显示或更新项目 issue 上下文',
	pr_comments: '显示或更新项目 PR 评论上下文',
	'privacy-settings': '显示本地隐私与存储设置',
	agents: '列出或查看 agent 与 teammate 任务',
	tasks: '管理后台任务',
	delete: '清理选定的会话',
	rules: '查看选定的规则',
};

/** Command descriptions mapping (English) */
const COMMAND_DESC_EN: Record<string, string> = {
	help: 'Show available commands',
	exit: 'Exit IllusionCode',
	clear: 'Clear current conversation history',
	new: 'Start new conversation and reset task ID',
	version: 'Show installed version',
	status: 'Show session status',
	context: 'Show system prompt or manage context window',
	summary: 'Summarize conversation history',
	compact: 'Compact earlier conversation history',
	cost: 'Show token usage and estimated cost',
	usage: 'Show usage and token estimates',
	stats: 'Show session statistics',
	memory: 'View and manage project memory',
	hooks: 'Show configured hooks',
	resume: 'Resume a recent saved session',
	export: 'Export current transcript',
	share: 'Create a shareable transcript snapshot',
	copy: 'Copy latest reply or specified text',
	rewind: 'Remove latest conversation turn',
	files: 'List current workspace files',
	init: 'Initialize project IllusionCode file',
	bridge: 'View bridge info and create bridge session',
	login: 'View auth status or save API Key',
	logout: 'Clear saved API Key',
	feedback: 'Save CLI feedback to local log',
	skills: 'List or show available skills',
	config: 'Show or update configuration',
	mcp: 'Show MCP status',
	plugin: 'Manage plugins',
	'reload-plugins': 'Reload current workspace plugin discovery',
	permissions: 'Show or update permission mode',
	plan: 'Toggle plan permission mode',
	fast: 'Show or update fast mode',
	effort: 'Show or update reasoning effort',
	passes: 'Show or update reasoning passes',
	turns: 'Show or update max agent turns',
	continue: 'Continue last tool loop after interruption',
	model: 'Show or update default model',
	language: 'Show or update UI language',
	'output-style': 'Show or update output style',
	doctor: 'Show environment diagnostics',
	diff: 'Show git diff output',
	branch: 'Show git branch info',
	commit: 'Show status or create git commit',
	issue: 'Show or update project issue context',
	pr_comments: 'Show or update project PR comments context',
	'privacy-settings': 'Show local privacy and storage settings',
	agents: 'List or view agent and teammate tasks',
	tasks: 'Manage background tasks',
	delete: 'Clean up selected sessions',
	rules: 'View selected rules',
};

export function App({config}: {config: FrontendConfig}): React.JSX.Element {
	return (
		<ThemeProvider>
			<AppInner config={config} />
		</ThemeProvider>
	);
}

function AppInner({config}: {config: FrontendConfig}): React.JSX.Element {
	const {exit} = useApp();
	const theme = useTheme();
	const [input, setInput] = useState('');
	const [modalInput, setModalInput] = useState('');
	const [scriptIndex, setScriptIndex] = useState(0);
	const [pickerIndex, setPickerIndex] = useState(0);
	const [selectModal, setSelectModal] = useState<SelectModalState>(null);
	const [selectIndex, setSelectIndex] = useState(0);
	const [permissionIndex, setPermissionIndex] = useState(2);
	const [pendingPermissionAck, setPendingPermissionAck] = useState(false);
	const session = useBackendSession(config, () => exit());
	const isPermissionModal = session.modal?.kind === 'permission';
	const language = normalizeLanguage(session.status.ui_language);
	const permissionRequestId =
		isPermissionModal && typeof session.modal?.request_id === 'string' ? String(session.modal.request_id) : '';
	const localizedPermissionOptions = PERMISSION_PROMPT_OPTIONS.map((opt) => {
		if (opt.value === 'allow') {
			return {...opt, label: t(language, 'allow')};
		}
		if (opt.value === 'always') {
			return {...opt, label: t(language, 'alwaysAllow')};
		}
		return {...opt, label: t(language, 'deny')};
	});

	// Current tool name for spinner
	const currentToolName = useMemo(() => {
		for (let i = session.staticItems.length - 1; i >= 0; i--) {
			const item = session.staticItems[i];
			if (item.role === 'tool') {
				return item.tool_name ?? 'tool';
			}
			if (item.role === 'tool_result' || item.role === 'assistant') {
				break;
			}
		}
		return undefined;
	}, [session.staticItems]);

	// Command hints
	const commandHints = useMemo(() => {
		if (!input.startsWith('/')) {
			return [] as string[];
		}
		const value = input.trimEnd();
		if (value === '') {
			return [] as string[];
		}
		const matches = session.commands.filter((cmd) => cmd.startsWith(value));
		if (value === '/') {
			const preferred = ['/language'];
			const boosted = preferred.filter((cmd) => matches.includes(cmd));
			const rest = matches.filter((cmd) => !preferred.includes(cmd));
			return [...boosted, ...rest];
		}
		return matches;
	}, [session.commands, input]);

	const canShowPicker = input.startsWith('/') && commandHints.length > 0;
	const showPicker = canShowPicker && !session.busy && !session.modal && !selectModal;

	useEffect(() => {
		setPickerIndex(0);
	}, [canShowPicker, commandHints.length, input]);

	// Handle backend-initiated select requests (e.g. /resume session list)
	useEffect(() => {
		if (!session.selectRequest) {
			return;
		}
		const req = session.selectRequest;
		if (req.options.length === 0) {
			session.setSelectRequest(null);
			return;
		}
		setSelectIndex(0);
		setSelectModal({
			title: req.title,
			options: req.options.map((o) => ({value: o.value, label: o.label, description: o.description})),
			onSelect: (value) => {
				session.sendRequest({type: 'apply_select_command', command: req.command, value});
				session.setBusy(true);
				setSelectModal(null);
			},
		});
		session.setSelectRequest(null);
	}, [session.selectRequest]);

	useEffect(() => {
		if (!isPermissionModal) {
			setPendingPermissionAck(false);
			return;
		}
		setPermissionIndex(1);
		setPendingPermissionAck(false);
	}, [permissionRequestId, isPermissionModal]);

	// Intercept special commands that need interactive UI
	const handleCommand = (cmd: string): boolean => {
		const trimmed = cmd.trim();

		// /permissions → show mode picker
		if (trimmed === '/permissions' || trimmed === '/permissions show') {
			const currentMode = String(session.status.permission_mode ?? 'default');
			const options = PERMISSION_MODES.map((opt) => ({
				...opt,
				active: opt.value === currentMode,
			}));
			const initialIndex = options.findIndex((o) => o.active);
			setSelectIndex(initialIndex >= 0 ? initialIndex : 0);
			setSelectModal({
				title: 'Permission Mode',
				options,
				onSelect: (value) => {
					session.sendRequest({type: 'submit_line', line: `/permissions set ${value}`});
					session.setBusy(true);
					setSelectModal(null);
				},
			});
			return true;
		}

		if (trimmed === '/language' || trimmed === '/language show') {
			const current = normalizeLanguage(session.status.ui_language);
			const options: SelectOption[] = [
				{value: 'set zh-CN', label: t(current, 'langZh'), description: '中文界面', active: current === 'zh-CN'},
				{value: 'set en', label: t(current, 'langEn'), description: 'English UI', active: current === 'en'},
			];
			const initialIndex = options.findIndex((o) => o.active);
			setSelectIndex(initialIndex >= 0 ? initialIndex : 0);
			setSelectModal({
				title: t(current, 'language'),
				options,
				onSelect: (value) => {
					session.sendRequest({type: 'submit_line', line: `/language ${value}`});
					session.setBusy(true);
					setSelectModal(null);
				},
			});
			return true;
		}

		// /help → show command list picker
		if (trimmed === '/help') {
			const descMap = language === 'en' ? COMMAND_DESC_EN : COMMAND_DESC_ZH;
			const options: SelectOption[] = session.commands.map((cmd) => ({
				value: cmd,
				label: cmd,
				description: descMap[cmd] ?? '',
			}));
			setSelectIndex(0);
			setSelectModal({
				title: t(language, 'helpTitle'),
				options,
				onSelect: (value) => {
					setInput(`${value} `);
					setSelectModal(null);
				},
			});
			return true;
		}

		// /plan → toggle plan mode
		if (trimmed === '/plan') {
			const currentMode = String(session.status.permission_mode ?? 'default');
			if (currentMode === 'plan') {
				session.sendRequest({type: 'submit_line', line: '/plan off'});
			} else {
				session.sendRequest({type: 'submit_line', line: '/plan on'});
			}
			session.setBusy(true);
			return true;
		}

		// /resume → request session list from backend (will trigger select_request)
		if (trimmed === '/resume') {
			session.sendRequest({type: 'list_sessions'});
			return true;
		}

		// /model → show model selector dropdown
		if (trimmed === '/model' || trimmed === '/model show') {
			session.sendRequest({type: 'select_command', command: 'model'});
			return true;
		}

		// /rewind → show message selector to pick rewind point
		if (trimmed === '/rewind') {
			session.sendRequest({type: 'select_command', command: 'rewind'});
			return true;
		}

		// /delete → show session picker for deletion
		if (trimmed === '/delete') {
			session.sendRequest({type: 'select_command', command: 'delete'});
			return true;
		}

		// /rules → show rule picker
		if (trimmed === '/rules') {
			session.sendRequest({type: 'select_command', command: 'rules'});
			return true;
		}

		// /new → clear conversation window and start fresh session
		if (trimmed === '/new') {
			session.clearStaticItems();
			session.sendRequest({type: 'submit_line', line: '/new'});
			session.setBusy(true);
			return true;
		}

		return false;
	};

	useInput((chunk, key) => {
		// Ctrl+C → 退出程序
		if (key.ctrl && chunk === 'c') {
			session.sendRequest({type: 'shutdown'});
			exit();
			return;
		}
		// Ctrl+X → 停止当前任务
		if (key.ctrl && chunk.toLowerCase() === 'x') {
			if (session.busy) {
				session.sendRequest({type: 'stop'});
			}
			return;
		}
		// Ctrl+T → 切换思考过程显示
		if (key.ctrl && chunk.toLowerCase() === 't') {
			session.setShowThinking((prev: boolean) => !prev);
			return;
		}

		// --- Select modal (permissions picker etc.) ---
		if (selectModal) {
			if (key.upArrow) {
				setSelectIndex((i) => Math.max(0, i - 1));
				return;
			}
			if (key.downArrow) {
				setSelectIndex((i) => Math.min(selectModal.options.length - 1, i + 1));
				return;
			}
			if (key.return) {
				const selected = selectModal.options[selectIndex];
				if (selected) {
					selectModal.onSelect(selected.value);
				}
				return;
			}
			if (key.escape) {
				setSelectModal(null);
				setInput('');
				return;
			}
			// Number keys for quick selection
			const num = parseInt(chunk, 10);
			if (num >= 1 && num <= selectModal.options.length) {
				const selected = selectModal.options[num - 1];
				if (selected) {
					selectModal.onSelect(selected.value);
				}
				return;
			}
			return;
		}

		// --- Scripted raw return ---
		if (rawReturnSubmit && key.return) {
			if (session.modal?.kind === 'question') {
				session.sendRequest({
					type: 'question_response',
					request_id: session.modal.request_id,
					answer: modalInput,
				});
				session.setModal(null);
				setModalInput('');
				return;
			}
			if (!session.modal && !session.busy && input.trim()) {
				onSubmit(input);
				return;
			}
		}

		// --- Permission modal (MUST be before busy check — modal appears while busy) ---
		if (isPermissionModal) {
			if (pendingPermissionAck) {
				return;
			}
			if (key.upArrow || key.downArrow) {
				setPermissionIndex((i) => {
					if (key.upArrow) return i <= 0 ? 2 : i - 1;
					return i >= 2 ? 0 : i + 1;
				});
				return;
			}
			if (key.return || key.escape) {
				if (!permissionRequestId) {
					return;
				}
				const selected = key.escape ? 'deny' : localizedPermissionOptions[permissionIndex]?.value;
				const allowed = selected === 'allow' || selected === 'always';
				session.sendRequest({
					type: 'permission_response',
					request_id: permissionRequestId,
					allowed,
					always_allow: selected === 'always',
					tool_name: String(session.modal?.tool_name ?? ''),
				});
				setPendingPermissionAck(true);
				return;
			}
			return;
		}

		// --- Question modal (also appears while busy) ---
		if (session.modal?.kind === 'question') {
			return;
		}

		// --- Ignore input while busy ---
		if (session.busy) {
			return;
		}

		// --- Command picker ---
		if (showPicker) {
			if (key.upArrow) {
				setPickerIndex((i) => Math.max(0, i - 1));
				return;
			}
			if (key.downArrow) {
				setPickerIndex((i) => Math.min(commandHints.length - 1, i + 1));
				return;
			}
			if (key.return) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setInput('');
					if (!handleCommand(selected)) {
						onSubmit(selected);
					}
				}
				return;
			}
			if (key.tab) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setInput(selected + ' ');
				}
				return;
			}
			if (key.escape) {
				setInput('');
				return;
			}
		}

		// Note: normal Enter submission is handled by TextInput's onSubmit in
		// PromptInput.  Do NOT duplicate it here — that causes double requests.
	});

	const onSubmit = (value: string): void => {
		if (session.modal?.kind === 'question') {
			session.sendRequest({
				type: 'question_response',
				request_id: session.modal.request_id,
				answer: value,
			});
			session.setModal(null);
			setModalInput('');
			return;
		}
		if (!value.trim() || session.busy || !session.ready) {
			return;
		}
		// Check if it's an interactive command
		if (handleCommand(value)) {
			setInput('');
			return;
		}
		session.sendRequest({type: 'submit_line', line: value});
		setInput('');
		session.setBusy(true);
	};

	// Scripted automation
	useEffect(() => {
		if (scriptIndex >= scriptedSteps.length) {
			return;
		}
		if (session.busy || session.modal || selectModal) {
			return;
		}
		const step = scriptedSteps[scriptIndex];
		const timer = setTimeout(() => {
			onSubmit(step);
			setScriptIndex((index) => index + 1);
		}, 200);
		return () => clearTimeout(timer);
	}, [scriptIndex, session.busy, session.modal, selectModal]);

	return (
		<Box flexDirection="column" height="100%">
			{/* Conversation area */}
			<Box flexDirection="column" flexGrow={1}>
				<ConversationView
					staticItems={session.staticItems}
					clearCount={session.clearCount}
					assistantBuffer={session.assistantBuffer}
					showWelcome={session.ready}
					showThinking={session.showThinking}
					language={language}
					commandPickerOpen={showPicker}
				/>
			</Box>

			<Box flexDirection="column" paddingX={1}>
			{/* Permission confirm modal */}
			{isPermissionModal ? (
				<SelectModal
					title={`Allow ${String(session.modal?.tool_name ?? 'tool')}?`}
					options={localizedPermissionOptions}
					selectedIndex={permissionIndex}
				/>
			) : null}

			{/* Backend modal (question, mcp auth) */}
			{session.modal && !isPermissionModal ? (
				<ModalHost
					modal={session.modal}
					modalInput={modalInput}
					setModalInput={setModalInput}
					onSubmit={onSubmit}
					language={language}
				/>
			) : null}

			{/* Frontend select modal (permissions picker, etc.) */}
			{selectModal ? (
				<SelectModal
					title={selectModal.title}
					options={selectModal.options}
					selectedIndex={selectIndex}
				/>
			) : null}

			{/* Command picker */}
			{showPicker ? (
				<CommandPicker hints={commandHints} selectedIndex={pickerIndex} totalCommands={session.commands.length} />
			) : null}

			{/* Todo panel */}
			{session.ready && session.todoItems.length > 0 ? (
				<TodoPanel items={session.todoItems} />
			) : null}

			{/* Swarm panel */}
			{session.ready && (session.swarmTeammates.length > 0 || session.swarmNotifications.length > 0) ? (
				<SwarmPanel teammates={session.swarmTeammates} notifications={session.swarmNotifications} />
			) : null}

			{/* Status bar (only after backend is ready) */}
			{session.ready ? (
				<StatusBar status={session.status} tasks={session.tasks} activeToolName={session.busy ? currentToolName : undefined} showThinking={session.showThinking} />
			) : null}

			{/* Input — show loading indicator until backend is ready */}
			{!session.ready ? (
				<Box>
					<Text color={theme.colors.warning}>{t(language, 'connecting')}</Text>
				</Box>
			) : session.modal || selectModal || pendingPermissionAck ? null : session.busy ? (
				<Box marginTop={1}>
					<Spinner
						todoItems={session.todoItems}
						language={language}
						toolName={currentToolName}
						sessionId={String(session.status.session_id ?? '')}
					/>
				</Box>
			) : (
				<PromptInput
					busy={session.busy}
					input={input}
					setInput={setInput}
					onSubmit={onSubmit}
					toolName={session.busy ? currentToolName : undefined}
					suppressSubmit={showPicker}
					language={language}
					todoItems={session.todoItems}
				/>
			)}

			{/* Keyboard hints (only after backend is ready) */}
			{session.ready && !session.modal && !session.busy && !selectModal && !pendingPermissionAck ? (
				<Box>
					<Text dimColor>
						<Text color={theme.colors.muted}>enter</Text> {t(language, 'send')}
						<Text> {theme.icons.middleDot} </Text>
						<Text color={theme.colors.muted}>/</Text> {t(language, 'commands')}
						<Text> {theme.icons.middleDot} </Text>
						<Text color={theme.colors.muted}>ctrl+c</Text> {t(language, 'exitProgram')}
						<Text> {theme.icons.middleDot} </Text>
						<Text color={theme.colors.muted}>ctrl+x</Text> {t(language, 'stopCurrentTask')}
						<Text> {theme.icons.middleDot} </Text>
						<Text color={theme.colors.muted}>ctrl+u</Text> {t(language, 'clearInput')}
					</Text>
				</Box>
			) : session.ready && session.busy && !session.modal && !selectModal ? (
				<Box marginTop={1}>
					<Text dimColor>
						<Text color={theme.colors.muted}>ctrl+c</Text> {t(language, 'exitProgram')}
						<Text> {theme.icons.middleDot} </Text>
						<Text color={theme.colors.muted}>ctrl+x</Text> {t(language, 'stopCurrentTask')}
					</Text>
				</Box>
			) : null}
			</Box>
		</Box>
	);
}
