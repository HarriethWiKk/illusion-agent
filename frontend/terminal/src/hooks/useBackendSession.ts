/**
 * @fileoverview 后端会话管理 Hook
 *
 * 本模块提供了 useBackendSession Hook，用于管理与后端进程的通信会话。
 * 主要功能包括：
 * - 启动和管理后端子进程
 * - 处理后端发送的 JSON 协议事件
 * - 管理会话状态（转录项、任务、命令等）
 * - 处理助手流式回复的缓冲和刷新
 * - 管理工具调用的生命周期
 * - 处理模态对话框和选择请求
 *
 * @module useBackendSession
 */

import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {spawn, type ChildProcess} from 'node:child_process';
import readline from 'node:readline';

import type {
	BackendEvent,
	BridgeSessionSnapshot,
	FrontendConfig,
	McpServerSnapshot,
	PendingToolCall,
	SelectRequestPayload,
	SwarmNotificationSnapshot,
	SwarmTeammateSnapshot,
	TaskSnapshot,
	TodoItemSnapshot,
	TranscriptItem,
} from '../types.js';

/**
 * 协议前缀标识
 * 后端发送的 JSON 消息都以此前缀开头，用于区分普通日志输出和协议消息
 */
const PROTOCOL_PREFIX = 'OHJSON:';

/**
 * 助手流式回复刷新间隔（毫秒）
 * 控制助手回复文本在屏幕上的更新频率，约 60fps
 */
const ASSISTANT_DELTA_FLUSH_MS = 16;

/**
 * 助手流式回复刷新字符阈值
 * 当缓冲的字符数达到此值时立即刷新，避免延迟感
 */
const ASSISTANT_DELTA_FLUSH_CHARS = 32;

/**
 * 工具调用行匹配正则表达式
 *
 * 匹配模型可能嵌入在助手文本中的工具调用预览行。
 * 例如："  bash (git add ...)" 或 "read (file_path: ...)"
 */
const TOOL_CALL_LINE_RE = /^\s{2,}\w[\w-]*\s*\(.*\)\s*$/;

/**
 * 从助手文本中移除工具调用预览行
 *
 * 模型有时会在回复中嵌入工具调用的预览文本，此函数将这些行移除，
 * 因为真正的工具调用会通过专门的事件处理。
 *
 * @param text - 原始助手文本
 * @returns 移除工具调用行后的文本；如果移除后为空则返回原始文本
 */
function stripToolCallLines(text: string): string {
	const lines = text.split('\n');
	const filtered = lines.filter((line) => !TOOL_CALL_LINE_RE.test(line));
	// 如果移除后为空，返回原始文本作为兜底
	return filtered.length > 0 ? filtered.join('\n') : text;
}

/**
 * 后端会话管理 Hook
 *
 * 管理与后端子进程的完整生命周期，包括：
 * - 启动后端进程并建立通信管道
 * - 接收并解析后端事件流
 * - 维护所有会话相关的状态
 * - 处理助手流式回复的缓冲和显示
 * - 管理工具调用的生命周期（开始、更新、完成）
 * - 处理各种模态对话框（权限确认、计划审批等）
 *
 * @param config - 前端配置对象，包含后端启动命令等信息
 * @param onExit - 后端退出时的回调函数
 * @returns 包含所有会话状态和操作方法的对象
 */
export function useBackendSession(config: FrontendConfig, onExit: (code?: number | null) => void) {
	/** 静态转录项列表（已完成的消息） */
	const [staticItems, setStaticItems] = useState<TranscriptItem[]>([]);
	/** 清空计数器，用于触发 ConversationView 重新渲染 */
	const [clearCount, setClearCount] = useState(0);
	/**
	 * 向静态列表追加新的转录项
	 * @param item - 要追加的转录项
	 */
	const pushStatic = useCallback((item: TranscriptItem): void => {
		setStaticItems((prev) => [...prev, item]);
	}, []);
	/** 助手回复缓冲区（当前正在流式接收的文本） */
	const [assistantBuffer, setAssistantBuffer] = useState('');
	/** 后端状态信息 */
	const [status, setStatus] = useState<Record<string, unknown>>({});
	/** 任务列表快照 */
	const [tasks, setTasks] = useState<TaskSnapshot[]>([]);
	/** 可用命令列表 */
	const [commands, setCommands] = useState<string[]>([]);
	/** MCP 服务器列表快照 */
	const [mcpServers, setMcpServers] = useState<McpServerSnapshot[]>([]);
	/** 桥接会话列表快照 */
	const [bridgeSessions, setBridgeSessions] = useState<BridgeSessionSnapshot[]>([]);
	/** 当前活动的模态对话框配置 */
	const [modal, setModal] = useState<Record<string, unknown> | null>(null);
	/** 后端发起的选择请求 */
	const [selectRequest, setSelectRequest] = useState<SelectRequestPayload | null>(null);
	/** 是否正在处理中（等待后端响应） */
	const [busy, setBusy] = useState(false);
	/** 后端是否已就绪 */
	const [ready, setReady] = useState(false);
	/** 是否显示思考过程 */
	const [showThinking, setShowThinking] = useState(true);
	/** 待办事项列表 */
	const [todoItems, setTodoItems] = useState<TodoItemSnapshot[]>([]);
	/** 待处理的工具调用列表 */
	const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[]>([]);
	/** 群体协作者列表 */
	const [swarmTeammates, setSwarmTeammates] = useState<SwarmTeammateSnapshot[]>([]);
	/** 群体协作通知列表 */
	const [swarmNotifications, setSwarmNotifications] = useState<SwarmNotificationSnapshot[]>([]);
	/** 后台代理标签文本 */
	const [bgAgentLabel, setBgAgentLabel] = useState<string | null>(null);
	/** 指令执行结果 */
	const [commandResult, setCommandResult] = useState<{
		text: string;
		type: 'success' | 'error' | 'info';
	} | null>(null);
	/** 后端子进程引用 */
	const childRef = useRef<ChildProcess | null>(null);
	/** 是否已发送初始提示词 */
	const sentInitialPrompt = useRef(false);

	// 流式增量可能逐 token 到达；为每个增量更新 Ink 状态会导致大量重渲染/闪烁。
	// 因此使用缓冲区并以约 60fps 的频率刷新。
	/** 助手回复显示缓冲区 */
	const assistantBufferRef = useRef('');
	/** 待刷新的助手增量文本 */
	const pendingAssistantDeltaRef = useRef('');
	/** 助手增量刷新定时器 */
	const assistantFlushTimerRef = useRef<NodeJS.Timeout | null>(null);
	/** 思考/推理过程缓冲区 */
	const reasoningBufferRef = useRef('');
	/** 原始缓冲区，用于思考标签处理和最终消息文本 */
	const rawBufferRef = useRef('');
	/**
	 * 标志位：防止助手文本在 tool_started 时被刷新后，
	 * assistant_complete 再次重复提交
	 */
	const assistantFlushedForToolRef = useRef(false);
	/** 待处理工具调用的 ref，避免 handleEvent 中的闭包过期问题 */
	const pendingToolCallsRef = useRef<PendingToolCall[]>([]);

	/**
	 * 刷新助手增量缓冲区
	 *
	 * 将待处理的增量文本追加到原始缓冲区，然后处理思考标签：
	 * - 如果不显示思考过程，移除所有 think 标签
	 * - 如果显示思考过程，移除标签但保留内容
	 * 将处理后的文本更新到显示缓冲区
	 */
	const flushAssistantDelta = (): void => {
		const pending = pendingAssistantDeltaRef.current;
		if (!pending) {
			return;
		}
		pendingAssistantDeltaRef.current = '';
		rawBufferRef.current += pending;

		// 处理思考标签以用于流式显示
		let displayText = rawBufferRef.current;
		if (!showThinking) {
			displayText = displayText
				.replace(/<think\b[^>]*>[\s\S]*?<\/think\b[^>]*>/gi, '')
				.replace(/<\/think\b[^>]*>/gi, '')
				.replace(/<think\b[^>]*>/gi, '')
				.replace(/<th(?:i(?:n(?:k)?)?)?\s*$/i, '');
		} else {
			displayText = displayText
				.replace(/<think\b[^>]*>/gi, '')
				.replace(/<\/think\b[^>]*>/gi, '')
				.replace(/<th(?:i(?:n(?:k)?)?)?\s*$/i, '');
		}
		if (showThinking && reasoningBufferRef.current.trim()) {
			const reasoning = reasoningBufferRef.current.trim();
			const text = displayText.trim();
			displayText = text ? `${reasoning}\n\n${text}` : reasoning;
		}
		assistantBufferRef.current = displayText;
		setAssistantBuffer(displayText);
	};

	/**
	 * 清空助手增量缓冲区
	 *
	 * 重置所有与助手流式回复相关的缓冲区和定时器，
	 * 并清空显示缓冲区。
	 */
	const clearAssistantDelta = (): void => {
		pendingAssistantDeltaRef.current = '';
		assistantBufferRef.current = '';
		rawBufferRef.current = '';
		if (assistantFlushTimerRef.current) {
			clearTimeout(assistantFlushTimerRef.current);
			assistantFlushTimerRef.current = null;
		}
		setAssistantBuffer('');
		reasoningBufferRef.current = '';
	};

	/**
	 * 向后端发送请求
	 *
	 * 将请求对象序列化为 JSON 并写入后端子进程的标准输入。
	 * 如果子进程不可用或输入流已销毁，则静默忽略。
	 *
	 * @param payload - 要发送的请求对象
	 */
	const sendRequest = (payload: Record<string, unknown>): void => {
		const child = childRef.current;
		if (!child || !child.stdin || child.stdin.destroyed) {
			return;
		}
		child.stdin.write(JSON.stringify(payload) + '\n');
	};

	/**
	 * 清空所有静态转录项
	 *
	 * 清除对话历史、重置清空计数器，并清空助手增量缓冲区。
	 * 用于实现 /new 或 /clear 命令。
	 */
	const clearStaticItems = (): void => {
		setStaticItems([]);
		setClearCount((c) => c + 1);
		clearAssistantDelta();
	};

	useEffect(() => {
		const [command, ...args] = config.backend_command;
		const child = spawn(command, args, {
			stdio: ['pipe', 'pipe', 'inherit'],
			env: process.env,
			detached: true,
			windowsHide: true,
		});
		childRef.current = child;

		const reader = readline.createInterface({input: child.stdout});
		reader.on('line', (line) => {
			if (!line.startsWith(PROTOCOL_PREFIX)) {
				pushStatic({role: 'log', text: line});
				return;
			}
			const event = JSON.parse(line.slice(PROTOCOL_PREFIX.length)) as BackendEvent;
			handleEvent(event);
		});

		child.on('exit', (code) => {
			pushStatic({role: 'system', text: `backend exited with code ${code ?? 0}`});
			process.exitCode = code ?? 0;
			onExit(code);
		});

		/**
		 * 启动后端子进程并建立通信
		 *
		 * 此效果函数在组件挂载时执行以下操作：
		 * 1. 根据配置启动后端子进程
		 * 2. 创建 readline 接口读取后端输出
		 * 3. 解析协议消息并分发到 handleEvent 处理
		 * 4. 设置进程退出时的清理逻辑
		 */
		// 确保子进程在父进程退出时被杀死（防止僵尸进程）
		const killChild = (): void => {
			if (!child.killed) {
				// 杀死进程组以确保 Python 后端及其所有子进程都被终止
				try {
					if (child.pid) {
						process.kill(-child.pid, 'SIGTERM');
					}
				} catch {
					child.kill('SIGTERM');
				}
			}
			if (assistantFlushTimerRef.current) {
				clearTimeout(assistantFlushTimerRef.current);
				assistantFlushTimerRef.current = null;
			}
		};
		process.on('exit', killChild);
		process.on('SIGINT', killChild);
		process.on('SIGTERM', killChild);

		return () => {
			reader.close();
			killChild();
			process.removeListener('exit', killChild);
			process.removeListener('SIGINT', killChild);
			process.removeListener('SIGTERM', killChild);
		};
	}, []);

	/**
	 * 处理后端事件
	 *
	 * 根据事件类型分发处理逻辑，支持的事件类型包括：
	 * - ready: 后端就绪，初始化状态
	 * - state_snapshot: 状态快照更新
	 * - tasks_snapshot: 任务列表更新
	 * - transcript_item: 新增转录项
	 * - assistant_delta: 助手流式回复增量
	 * - assistant_complete: 助手回复完成
	 * - line_complete: 行处理完成
	 * - tool_started/tool_completed: 工具调用生命周期
	 * - tool_input_updated: 工具参数更新
	 * - clear_transcript/replace_transcript: 转录项管理
	 * - select_request: 选择请求
	 * - modal_request: 模态对话框请求
	 * - error: 错误事件
	 * - todo_update: 待办事项更新
	 * - swarm_status: 群体协作状态更新
	 * - plan_mode_change: 计划模式变更
	 * - command_result: 指令执行结果
	 * - bg_agent_status: 后台代理状态
	 * - shutdown: 关闭信号
	 *
	 * @param event - 后端事件对象
	 */
	const handleEvent = (event: BackendEvent): void => {
		if (event.type === 'ready') {
			setReady(true);
			setStatus(event.state ?? {});
			const showThinkingFromState = event.state?.show_thinking;
			if (typeof showThinkingFromState === 'boolean') {
				setShowThinking(showThinkingFromState);
			}
			setTasks(event.tasks ?? []);
			setCommands(event.commands ?? []);
			setMcpServers(event.mcp_servers ?? []);
			setBridgeSessions(event.bridge_sessions ?? []);
			if (config.initial_prompt && !sentInitialPrompt.current) {
				sentInitialPrompt.current = true;
				sendRequest({type: 'submit_line', line: config.initial_prompt});
				setBusy(true);
			}
			return;
		}
		if (event.type === 'state_snapshot') {
			setStatus(event.state ?? {});
			const showThinkingFromState = event.state?.show_thinking;
			if (typeof showThinkingFromState === 'boolean') {
				setShowThinking(showThinkingFromState);
			}
			setMcpServers(event.mcp_servers ?? []);
			setBridgeSessions(event.bridge_sessions ?? []);
			return;
		}
		if (event.type === 'tasks_snapshot') {
			setTasks(event.tasks ?? []);
			return;
		}
		if (event.type === 'transcript_item' && event.item) {
			pushStatic(event.item as TranscriptItem);
			return;
		}
		if (event.type === 'assistant_delta') {
			assistantFlushedForToolRef.current = false;
			if (event.reasoning) {
				reasoningBufferRef.current += event.reasoning;
			}
			const delta = event.message ?? '';
			if (!delta) {
				if (showThinking && reasoningBufferRef.current.trim()) {
					const display = reasoningBufferRef.current.trim();
					assistantBufferRef.current = display;
					setAssistantBuffer(display);
				}
				return;
			}
			pendingAssistantDeltaRef.current += delta;
			if (pendingAssistantDeltaRef.current.length >= ASSISTANT_DELTA_FLUSH_CHARS) {
				flushAssistantDelta();
				return;
			}
			if (!assistantFlushTimerRef.current) {
				assistantFlushTimerRef.current = setTimeout(() => {
					assistantFlushTimerRef.current = null;
					flushAssistantDelta();
				}, ASSISTANT_DELTA_FLUSH_MS);
			}
			return;
		}
		if (event.type === 'assistant_complete') {
			if (assistantFlushTimerRef.current) {
				clearTimeout(assistantFlushTimerRef.current);
				assistantFlushTimerRef.current = null;
			}
			flushAssistantDelta();

			// 如果 tool_started 已经将文本提交到静态列表，则跳过
			if (!assistantFlushedForToolRef.current) {
				const text = event.message ?? rawBufferRef.current;
				const reasoning = (event.reasoning ?? reasoningBufferRef.current) || undefined;
				if (text.trim() || (reasoning ?? '').trim()) {
					pushStatic({role: 'assistant', text: stripToolCallLines(text), reasoning});
				}
			}
			assistantFlushedForToolRef.current = false;

			clearAssistantDelta();
			return;
		}
		if (event.type === 'line_complete') {
			// 如果行在没有 assistant_complete 的情况下结束（例如发生错误），
			// 确保不会在屏幕上留下过期的流式文本
			clearAssistantDelta();
			pendingToolCallsRef.current = [];
			setPendingToolCalls([]);
			setBgAgentLabel(null);
			setBusy(false);
			return;
		}
		if ((event.type === 'tool_started' || event.type === 'tool_completed') && event.item) {
			if (event.type === 'tool_started') {
				// 在工具调用出现之前，将任何待处理的助手文本提交到静态列表
				if (rawBufferRef.current.trim() || pendingAssistantDeltaRef.current || reasoningBufferRef.current.trim()) {
					if (assistantFlushTimerRef.current) {
						clearTimeout(assistantFlushTimerRef.current);
						assistantFlushTimerRef.current = null;
					}
					flushAssistantDelta();
					const text = rawBufferRef.current;
					const reasoning = reasoningBufferRef.current || undefined;
					if (text.trim() || (reasoning ?? '').trim()) {
						pushStatic({
							role: 'assistant',
							text: stripToolCallLines(text),
							reasoning,
						});
					}
					clearAssistantDelta();
					assistantFlushedForToolRef.current = true;
				}
				setBusy(true);
				// 工具调用全过程保持在 pendingToolCalls 状态（非 Static），
				// 以便对 ● 做闪烁动画，直到 tool_completed 才推入 staticItems
				const toolInput = event.item.tool_input ?? event.tool_input;
				const toolUseId = event.item.tool_use_id ?? event.tool_use_id ?? '';
				const pendingCall: PendingToolCall = {
					tool_name: event.item.tool_name ?? event.tool_name ?? 'tool',
					tool_use_id: toolUseId,
					tool_input: (toolInput && Object.keys(toolInput).length > 0) ? toolInput : undefined,
				};
				pendingToolCallsRef.current = [...pendingToolCallsRef.current, pendingCall];
				setPendingToolCalls(pendingToolCallsRef.current);
				return;
			}
			// tool_completed: 将工具项和结果一并推入 staticItems
			if (event.type === 'tool_completed') {
				const toolUseId = event.item.tool_use_id ?? event.tool_use_id ?? '';
				const pendingIdx = pendingToolCallsRef.current.findIndex(p => p.tool_use_id === toolUseId);
				if (pendingIdx !== -1) {
					const pending = pendingToolCallsRef.current[pendingIdx];
					pendingToolCallsRef.current = pendingToolCallsRef.current.filter(p => p.tool_use_id !== toolUseId);
					setPendingToolCalls(pendingToolCallsRef.current);
					pushStatic({
						role: 'tool',
						text: pending.tool_name,
						tool_name: pending.tool_name,
						tool_input: pending.tool_input,
						tool_use_id: pending.tool_use_id || undefined,
					});
				}
				const enrichedItem: TranscriptItem = {
					...event.item,
					tool_name: event.item.tool_name ?? event.tool_name ?? undefined,
					tool_input: event.item.tool_input ?? undefined,
					tool_use_id: event.item.tool_use_id ?? event.tool_use_id ?? undefined,
					is_error: event.item.is_error ?? event.is_error ?? undefined,
					structured_output: event.structured_output ?? undefined,
					output_type: event.output_type ?? undefined,
					tool_metadata: event.tool_metadata ?? undefined,
				};
				pushStatic(enrichedItem);
			}
			return;
		}
		if (event.type === 'tool_input_updated') {
			// 后端发送了完整的工具参数，更新 pendingToolCalls 中对应项的 tool_input
			const toolUseId = event.tool_use_id;
			pendingToolCallsRef.current = pendingToolCallsRef.current.map(p =>
				p.tool_use_id === toolUseId
					? {...p, tool_input: event.tool_input ?? undefined}
					: p,
			);
			setPendingToolCalls(pendingToolCallsRef.current);
			return;
		}
		if (event.type === 'tool_progress') {
			// 流式进度消息，更新对应 pendingToolCall 的 progressMessages
			const toolUseId = event.tool_use_id;
			if (toolUseId) {
				pendingToolCallsRef.current = pendingToolCallsRef.current.map(p =>
					p.tool_use_id === toolUseId
						? {
							...p,
							progressMessages: [
								...(p.progressMessages ?? []),
								event.message ?? '',
							].slice(-10),
						}
						: p,
				);
				setPendingToolCalls(pendingToolCallsRef.current);
			}
			return;
		}
		if (event.type === 'tool_reset') {
			// 清理前端工具状态
			const toolUseId = event.tool_use_id;
			if (toolUseId) {
				pendingToolCallsRef.current = pendingToolCallsRef.current.filter(
					(p) => p.tool_use_id !== toolUseId,
				);
			} else {
				pendingToolCallsRef.current = [];
			}
			setPendingToolCalls(pendingToolCallsRef.current);
			return;
		}
		if (event.type === 'session_rewind') {
			// 会话回退，清空指定位置之后的所有 items
			const rewindToIndex = event.rewind_to_index ?? 0;
			setStaticItems((prev) => prev.slice(0, rewindToIndex));
			setClearCount((c) => c + 1);
			clearAssistantDelta();
			pendingToolCallsRef.current = [];
			setPendingToolCalls([]);
			return;
		}
		if (event.type === 'clear_transcript') {
			setStaticItems([]);
			setClearCount((c) => c + 1);
			clearAssistantDelta();
			pendingToolCallsRef.current = [];
			setPendingToolCalls([]);
			return;
		}
		if (event.type === 'replace_transcript' && event.items) {
			const newItems = (event.items as TranscriptItem[]).filter((item: TranscriptItem) => {
				if (item.role === 'user' && item.text.startsWith('/')) {
					return false;
				}
				return true;
			});
			setStaticItems(newItems);
			setClearCount((c) => c + 1);
			clearAssistantDelta();
			pendingToolCallsRef.current = [];
			setPendingToolCalls([]);
			return;
		}
		if (event.type === 'select_request') {
			const m = event.modal ?? {};
			setSelectRequest({
				title: String(m.title ?? 'Select'),
				command: String(m.command ?? ''),
				options: event.select_options ?? [],
			});
			setBusy(false);
			return;
		}
		if (event.type === 'modal_request') {
			setModal(event.modal ?? null);
			return;
		}
		if (event.type === 'error') {
			pushStatic({role: 'system', text: `error: ${event.message ?? 'unknown error'}`});
			clearAssistantDelta();
			setBusy(false);
			return;
		}
		if (event.type === 'todo_update') {
			if (event.todo_items != null) {
				setTodoItems(event.todo_items);
			}
			return;
		}
		if (event.type === 'swarm_status') {
			if (event.swarm_teammates != null) {
				setSwarmTeammates(event.swarm_teammates);
			}
			if (event.swarm_notifications != null) {
				setSwarmNotifications((prev) => [...prev, ...event.swarm_notifications!].slice(-20));
			}
			return;
		}
		if (event.type === 'plan_mode_change') {
			if (event.plan_mode != null) {
				setStatus((s) => ({...s, permission_mode: event.plan_mode}));
			}
			return;
		}
		if (event.type === 'command_result' && event.command_result_data) {
			setCommandResult({
				text: event.command_result_data.message,
				type: event.command_result_data.type || 'info',
			});
			return;
		}
		if (event.type === 'bg_agent_status') {
			setBgAgentLabel(event.message ?? null);
			return;
		}
		if (event.type === 'shutdown') {
			onExit(0);
		}
	};

	return useMemo(
		() => ({
			staticItems,
			assistantBuffer,
			clearCount,
			showThinking,
			status,
			tasks,
			commands,
			mcpServers,
			bridgeSessions,
			modal,
			selectRequest,
			busy,
			ready,
			todoItems,
			pendingToolCalls,
			swarmTeammates,
			swarmNotifications,
			bgAgentLabel,
			commandResult,
			setCommandResult,
			setModal,
			setSelectRequest,
			setBusy,
			sendRequest,
			clearStaticItems,
			pushStatic,
		}),
		[assistantBuffer, bridgeSessions, busy, clearCount, commandResult, commands, mcpServers, modal, pendingToolCalls, ready, selectRequest, showThinking, staticItems, status, swarmNotifications, swarmTeammates, tasks, todoItems, bgAgentLabel]
	);
}
