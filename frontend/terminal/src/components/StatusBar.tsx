/**
 * @fileoverview 状态栏组件
 *
 * 显示当前会话的状态信息，包括：
 * - 模型名称
 * - Token 使用量（输入/输出）
 * - 权限模式
 * - 活动任务数
 * - MCP 服务器连接数
 * - 后台代理数
 *
 * @module StatusBar
 */

import React, {useEffect, useState} from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TaskSnapshot} from '../types.js';
import {fmtTokens} from '../utils/fmtTokens.js';

/** 分隔符 */
const SEP = ' · ';

/**
 * 自动模式指示器
 *
 * 当处于自动权限模式时显示的标识。
 */
function AutoModeIndicator(): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box marginLeft={1}>
			<Text backgroundColor={theme.colors.illusion} color={theme.colors.background} bold>
				{' AUTO '}
			</Text>
		</Box>
	);
}

function TokenDisplay({
	inputTokens,
	outputTokens,
	color,
}: {
	inputTokens: number;
	outputTokens: number;
	color: string;
}): React.JSX.Element {
	return (
		<Text color={color}>
			<Text dimColor>{fmtTokens(inputTokens)}</Text>
			<Text dimColor>↓</Text>
			<Text> </Text>
			<Text dimColor>{fmtTokens(outputTokens)}</Text>
			<Text dimColor>↑</Text>
		</Text>
	);
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
 */
function AgentIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	const [visible, setVisible] = useState(true);

	useEffect(() => {
		const interval = setInterval(() => setVisible(v => !v), 500);
		return () => clearInterval(interval);
	}, []);

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
}: {
	status: Record<string, unknown>;
	tasks: TaskSnapshot[];
	noMarginTop?: boolean;
}): React.JSX.Element {
	const theme = useTheme();
	const model = String(status.model ?? 'unknown');
	const mode = String(status.permission_mode ?? 'default');
	const taskCount = tasks.filter(
		(task) => task.status === 'pending' || task.status === 'in_progress'
	).length;
	const mcpCount = Number(status.mcp_connected ?? 0);
	const agentCount = Number(status.agent_count ?? 0);
	const inputTokens = Number(status.input_tokens ?? 0);
	const outputTokens = Number(status.output_tokens ?? 0);
	const isAutoMode = mode === 'full_auto' || mode === 'auto';

	return (
		<Box flexDirection="column" marginTop={noMarginTop ? 0 : 1}>
			{!noMarginTop ? (
				<Box flexDirection="row">
					<Text color={theme.colors.text}>{'─'.repeat(60)}</Text>
				</Box>
			) : null}
			<Box flexDirection="row" alignItems="center">
				<Text color={theme.colors.illusion}>{model}</Text>
				{(inputTokens > 0 || outputTokens > 0) ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<TokenDisplay inputTokens={inputTokens} outputTokens={outputTokens} color={theme.colors.illusion} />
					</>
				) : null}
				{mode !== 'default' ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<Text color={theme.colors.illusion}>{mode}</Text>
					</>
				) : null}
				{taskCount > 0 ? (
					<>
						<Text color={theme.colors.illusion}>{SEP}</Text>
						<TaskIndicator count={taskCount} />
					</>
				) : null}
				{mcpCount > 0 ? (
					<McpIndicator count={mcpCount} />
				) : null}
				{agentCount > 0 ? <AgentIndicator count={agentCount} /> : null}
				<Box flexGrow={1} />
				{isAutoMode ? <AutoModeIndicator /> : null}
		</Box>
		</Box>
	);
}
