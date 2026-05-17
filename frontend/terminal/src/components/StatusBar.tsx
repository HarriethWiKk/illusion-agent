import React, {useEffect, useState} from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import type {TaskSnapshot} from '../types.js';

const SEP = ' · ';

function AutoModeIndicator(): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box marginLeft={1}>
			<Text backgroundColor={theme.colors.success} color={theme.colors.background} bold>
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
			<Text dimColor>{formatNum(inputTokens)}</Text>
			<Text dimColor>↓</Text>
			<Text> </Text>
			<Text dimColor>{formatNum(outputTokens)}</Text>
			<Text dimColor>↑</Text>
		</Text>
	);
}

function TaskIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box>
			<Text color={theme.colors.info}>{theme.icons.inProgress}</Text>
			<Text color={theme.colors.info}> {count} task{count !== 1 ? 's' : ''}</Text>
		</Box>
	);
}

function McpIndicator({count}: {count: number}): React.JSX.Element {
	const theme = useTheme();
	return (
		<Box>
			<Text color={theme.colors.permission}> · {count} MCP</Text>
		</Box>
	);
}

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
			<Text color={theme.colors.permission}> · {count} agent{count !== 1 ? 's' : ''}</Text>
		</Box>
	);
}

export function StatusBar({
	status,
	tasks,
}: {
	status: Record<string, unknown>;
	tasks: TaskSnapshot[];
}): React.JSX.Element {
	const theme = useTheme();
	const model = String(status.model ?? 'unknown');
	const mode = String(status.permission_mode ?? 'default');
	const taskCount = tasks.length;
	const mcpCount = Number(status.mcp_connected ?? 0);
	const agentCount = Number(status.agent_count ?? 0);
	const inputTokens = Number(status.input_tokens ?? 0);
	const outputTokens = Number(status.output_tokens ?? 0);
	const isAutoMode = mode === 'full_auto' || mode === 'auto';

	return (
		<Box flexDirection="column" marginTop={1}>
			<Box flexDirection="row">
				<Text color={theme.colors.text}>{'─'.repeat(60)}</Text>
			</Box>
			<Box flexDirection="row" alignItems="center">
				<Text color={theme.colors.illusion}>{model}</Text>
				{(inputTokens > 0 || outputTokens > 0) ? (
					<>
						<Text dimColor>{SEP}</Text>
						<TokenDisplay inputTokens={inputTokens} outputTokens={outputTokens} color={theme.colors.muted} />
					</>
				) : null}
				{mode !== 'default' ? (
					<>
						<Text dimColor>{SEP}</Text>
						<Text dimColor>{mode}</Text>
					</>
				) : null}
				{taskCount > 0 ? (
					<>
						<Text dimColor>{SEP}</Text>
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

function formatNum(n: number): string {
	if (n >= 1000000) {
		return `${(n / 1000000).toFixed(1)}M`;
	}
	if (n >= 1000) {
		return `${(n / 1000).toFixed(1)}k`;
	}
	return String(n);
}
