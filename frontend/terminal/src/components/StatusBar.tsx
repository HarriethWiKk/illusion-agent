/**
 * @fileoverview 状态栏组件
 *
 * 显示当前会话的状态信息，包括：
 * - 模型名称
 * - 权限模式
 * - MCP 服务器连接数
 * - 活动任务数
 * - Token 使用量（输入/输出）
 * - 后台代理数
 *
 * @module StatusBar
 */

import React from 'react';
import {Box, Text} from 'ink';

import {useBlink} from '../hooks/useBlink.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {TaskSnapshot} from '../types.js';
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
	inputTokens,
	outputTokens,
	color,
	busy,
}: {
	inputTokens: number;
	outputTokens: number;
	color: string;
	busy: boolean;
}): React.JSX.Element {
	// busy 时与 ● 同频闪烁（useBlink 共享全局动画时钟）
	const visible = useBlink(busy);
	const text = `${fmtTokens(inputTokens)}↓ ${fmtTokens(outputTokens)}↑`;
	if (!visible) {
		return <Text>{' '.repeat(stringWidth(text))}</Text>;
	}
	return <Text color={color}>{text}</Text>;
}

/**
 * 任务指示器
 *
 * 显示当前活动任务的数量。
 */
function TaskIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box>
			<Text color={theme.colors.illusion}>{count} task{count !== 1 ? 's' : ''}</Text>
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
 */
function AgentIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	const visible = useBlink(true);

	if (!visible) {
		return <Box><Text> </Text></Box>;
	}

	return (
		<Box>
			<Text color={theme.colors.illusion}> · {count} agent{count !== 1 ? 's' : ''}</Text>
		</Box>
	);
}

export function StatusBar({
	status,
	tasks,
	noMarginTop,
	busy,
}: {
	status: Record<string, unknown>;
	tasks: TaskSnapshot[];
	noMarginTop?: boolean;
	busy: boolean;
}): React.JSX.Element {
	const theme = useTheme();
	const model = String(status.model ?? 'unknown');
	const modeRaw = String(status.permission_mode ?? 'default');
	const mode = MODE_LABELS[modeRaw] ?? modeRaw;
	const taskCount = tasks.filter(
		(task) => task.status === 'pending' || task.status === 'in_progress'
	).length;
	const mcpCount = Number(status.mcp_connected ?? 0);
	const agentCount = Number(status.agent_count ?? 0);
	const inputTokens = Number(status.input_tokens ?? 0);
	const outputTokens = Number(status.output_tokens ?? 0);

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
				{mcpCount > 0 ? (
					<McpIndicator count={mcpCount} />
				) : null}
				{taskCount > 0 ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<TaskIndicator count={taskCount} />
					</>
				) : null}
				{(inputTokens > 0 || outputTokens > 0) ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<TokenDisplay inputTokens={inputTokens} outputTokens={outputTokens} color={theme.colors.illusion} busy={busy} />
					</>
				) : null}
				{agentCount > 0 ? <AgentIndicator count={agentCount} /> : null}
			</Box>
		</Box>
	);
}
