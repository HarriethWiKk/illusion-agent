/**
 * @fileoverview 状态栏组件
 *
 * 显示当前会话的状态信息，顺序为：
 * - 模型名称
 * - 权限模式
 * - 思考强度（effort）
 * - MCP 服务器连接数
 * - Token 使用量（输入/输出，含缓存命中率）
 * - 活动 shell 数（前台+后台 bash/powershell）
 * - 活动代理数（前台+后台 agents）
 *
 * @module StatusBar
 */

import React, {useMemo} from 'react';
import {Box, Text} from 'ink';

import {useBlink} from '../hooks/useBlink.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {PendingToolCall, TaskSnapshot} from '../types.js';
import {fmtTokens} from '../utils/fmtTokens.js';
import {stringWidth} from '../utils/markdown.js';

/** 分隔符 */
const SEP = ' · ';

/** 模式显示标签 */
const MODE_LABELS: Record<string, string> = {
	default: 'Default',
	plan: 'Plan Mode',
	full_auto: 'Auto',
};

function TokenDisplay({
	cacheRead,
	cacheCreation,
	inputTokens,
	outputTokens,
	color,
	busy,
}: {
	cacheRead: number;
	cacheCreation: number;
	inputTokens: number;
	outputTokens: number;
	color: string;
	busy: boolean;
}): React.JSX.Element {
	// busy 时与 ● 同频闪烁（useBlink 共享全局动画时钟）
	const visible = useBlink(busy);
	// cached = cache_read + cache_creation（状态栏显示总量）
	const cached = cacheRead + cacheCreation;
	const totalInput = cached + inputTokens;
	// 缓存命中率 = cache_read / (cache_read + cache_creation + input_tokens)，保留一位小数
	const hitRate = totalInput > 0 ? Math.round((cacheRead * 1000) / totalInput) / 10 : 0;
	const text = `${fmtTokens(cached)}↓ ${fmtTokens(inputTokens)}↓ ${fmtTokens(outputTokens)}↑${totalInput > 0 ? ` ${hitRate.toFixed(1)}%` : ''}`;
	if (!visible) {
		return <Text>{' '.repeat(stringWidth(text))}</Text>;
	}
	return (
		<Text>
			<Text color={color}>{fmtTokens(cached)}↓ </Text>
			<Text color={color} dimColor>{fmtTokens(inputTokens)}↓ </Text>
			<Text color={color}>{fmtTokens(outputTokens)}↑</Text>
			{totalInput > 0 ? <Text color={color}> {hitRate.toFixed(1)}%</Text> : null}
		</Text>
	);
}

/**
 * Shell 指示器
 *
 * 显示当前活动 shell（前台+后台 bash/powershell）的数量，带有闪烁动画效果。
 * 使用 useBlink 共享全局动画时钟，与 ● 、TokenDisplay 和 AgentIndicator 同频闪烁。
 * 只要存在活动 shell 就闪烁（包括后台任务运行中非 busy 状态）。
 */
function ShellIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	const visible = useBlink(true);
	const text = ` · ${count} shell${count !== 1 ? 's' : ''}`;

	if (!visible) {
		return <Box><Text>{' '.repeat(stringWidth(text))}</Text></Box>;
	}

	return (
		<Box>
			<Text color={theme.colors.illusion}>{text}</Text>
		</Box>
	);
}

function McpIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box>
			<Text color={theme.colors.illusion}> · {count} MCP</Text>
		</Box>
	);
}

/**
 * 代理指示器
 *
 * 显示当前运行的后台代理数量，带有闪烁动画效果。
 * 使用 useBlink 共享全局动画时钟，与 ● 和 TokenDisplay 同频闪烁。
 * 闪烁 off 阶段保留宽度占位，避免布局跳动。
 */
function AgentIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	const visible = useBlink(true);
	const text = ` · ${count} agent${count !== 1 ? 's' : ''}`;

	if (!visible) {
		return <Box><Text>{' '.repeat(stringWidth(text))}</Text></Box>;
	}

	return (
		<Box>
			<Text color={theme.colors.illusion}>{text}</Text>
		</Box>
	);
}

/** 后台 agent 任务的 type 集合（in_process_agent/local_agent/remote_agent/in_process_teammate） */
const AGENT_TASK_TYPES = new Set(['in_process_agent', 'local_agent', 'remote_agent', 'in_process_teammate']);

export function StatusBar({
	status,
	tasks,
	pendingToolCalls,
	noMarginTop,
	busy,
}: {
	status: Record<string, unknown>;
	tasks: TaskSnapshot[];
	pendingToolCalls: PendingToolCall[];
	noMarginTop?: boolean;
	busy: boolean;
}): React.JSX.Element {
	const theme = useTheme();
	const model = String(status.model ?? 'unknown');
	const modeRaw = String(status.permission_mode ?? 'default');
	const mode = MODE_LABELS[modeRaw] ?? modeRaw;
	// shells = 前台 shell（pendingToolCalls 中 bash/powershell）+ 后台 shell（tasks 中 local_bash 活跃）
	const shellCount = useMemo(() =>
		pendingToolCalls.filter((p) => p.tool_name === 'bash' || p.tool_name === 'powershell').length
		+ tasks.filter((t) => t.type === 'local_bash' && (t.status === 'pending' || t.status === 'in_progress')).length,
	[pendingToolCalls, tasks]);
	// agents = 前台 agent（pendingToolCalls 中 agent）+ 后台 agent（tasks 中 agent 类型活跃）
	const agentCount = useMemo(() =>
		pendingToolCalls.filter((p) => p.tool_name === 'agent').length
		+ tasks.filter((t) => AGENT_TASK_TYPES.has(t.type) && (t.status === 'pending' || t.status === 'in_progress')).length,
	[pendingToolCalls, tasks]);
	const mcpCount = Number(status.mcp_connected ?? 0);
	// 思考强度（effort）固化在状态栏，始终显示，首字母大写
	const effortRaw = String(status.effort ?? 'medium');
	const effort = effortRaw.charAt(0).toUpperCase() + effortRaw.slice(1);
	// 最后一次 API 调用的真实分项（非累积值）
	const cacheReadTokens = Number(status.context_cache_read ?? 0);
	const cacheCreationTokens = Number(status.context_cache_creation ?? 0);
	const inputTokens = Number(status.context_input ?? 0);
	const outputTokens = Number(status.context_output ?? 0);

	return (
		<Box flexDirection="column" marginTop={noMarginTop ? 0 : 1}>
			{!noMarginTop ? (
				<Box flexDirection="row">
					<Text color={theme.colors.text}>{'─'.repeat(60)}</Text>
				</Box>
			) : null}
			<Box flexDirection="row" alignItems="center">
				<Text color={theme.colors.illusion}>{model}</Text>
				<>
					<Text color={theme.colors.illusion}>{SEP}</Text>
					<Text color={theme.colors.illusion}>{mode}</Text>
				</>
				{/* 思考强度（effort）固化在状态栏 */}
				<>
					<Text color={theme.colors.illusion}>{SEP}</Text>
					<Text color={theme.colors.illusion}>{effort}</Text>
				</>
				{mcpCount > 0 ? (
					<McpIndicator count={mcpCount} />
				) : null}
				{(inputTokens > 0 || outputTokens > 0 || cacheReadTokens > 0 || cacheCreationTokens > 0) ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<TokenDisplay
							cacheRead={cacheReadTokens}
							cacheCreation={cacheCreationTokens}
							inputTokens={inputTokens}
							outputTokens={outputTokens}
							color={theme.colors.illusion}
							busy={busy}
						/>
					</>
				) : null}
				{shellCount > 0 ? <ShellIndicator count={shellCount} /> : null}
				{agentCount > 0 ? <AgentIndicator count={agentCount} /> : null}
			</Box>
		</Box>
	);
}
