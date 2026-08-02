/**
 * @fileoverview 侧边面板组件
 *
 * 显示应用状态信息的侧边面板，包含多个子面板：
 * - 状态面板（模型、提供商、权限等）
 * - 任务面板
 * - MCP 服务器面板
 * - 命令面板
 *
 * @module SidePanel
 */

import React from 'react';
import {Box, Text} from 'ink';

import type {ThemeConfig} from '../theme/ThemeContext.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {McpServerSnapshot, TaskSnapshot} from '../types.js';

/**
 * 侧边面板组件
 *
 * 组合多个子面板显示完整的应用状态信息。
 *
 * @param props - 组件属性
 * @param props.status - 后端状态对象
 * @param props.tasks - 任务列表
 * @param props.commands - 可用命令列表
 * @param props.commandHints - 命令提示列表
 * @param props.mcpServers - MCP 服务器列表
 * @returns 返回侧边面板的 JSX 元素
 */
export function SidePanel({
	status,
	tasks,
	commands,
	commandHints,
	mcpServers,
}: {
	status: Record<string, unknown>;
	tasks: TaskSnapshot[];
	commands: string[];
	commandHints: string[];
	mcpServers: McpServerSnapshot[];
}): React.JSX.Element {
	const theme = useTheme();

	return (
		<Box flexDirection="column" width="32%">
			<StatusPanel status={status} theme={theme} />
			<TaskPanel tasks={tasks} theme={theme} />
			<McpPanel servers={mcpServers} theme={theme} />
			<CommandPanel commands={commands} hints={commandHints} theme={theme} />
		</Box>
	);
}

/**
 * 状态面板组件
 *
 * 显示当前会话的状态信息，包括模型、提供商、权限模式等。
 */
function StatusPanel({status, theme}: {status: Record<string, unknown>; theme: ThemeConfig}): React.JSX.Element {
	const agentCount = Number(status.agent_count ?? 0);
	return (
		<>
			<Box marginBottom={1}>
				<Text color={theme.colors.primary} bold>{theme.icons.chevron} Status</Text>
			</Box>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.muted} paddingX={1} marginBottom={1}>
				<Text><Text dimColor>model:</Text> <Text color={theme.colors.accent}>{String(status.model ?? 'unknown')}</Text></Text>
				{agentCount > 0 ? (
					<Text><Text dimColor>agents:</Text> <Text color={theme.colors.illusion}>{agentCount} running</Text></Text>
				) : null}
				<Text><Text dimColor>provider:</Text> <Text color={theme.colors.accent}>{String(status.provider ?? 'unknown')}</Text></Text>
				<Text><Text dimColor>auth:</Text> <Text color={theme.colors.accent}>{String(status.auth_status ?? 'unknown')}</Text></Text>
				<Text><Text dimColor>permission:</Text> <Text color={theme.colors.accent}>{String(status.permission_mode ?? 'unknown')}</Text></Text>
				<Text><Text dimColor>cwd:</Text> <Text color={theme.colors.accent}>{String(status.cwd ?? '.')}</Text></Text>
				<Text><Text dimColor>language:</Text> <Text color={theme.colors.accent}>{String(status.ui_language ?? 'zh-CN')}</Text></Text>
				<Text><Text dimColor>effort:</Text> <Text color={theme.colors.accent}>{String(status.effort ?? 'medium')}</Text></Text>
			</Box>
		</>
	);
}

/**
 * 任务面板组件
 *
 * 显示当前活动的任务列表。
 */
function TaskPanel({tasks, theme}: {tasks: TaskSnapshot[]; theme: ThemeConfig}): React.JSX.Element {
	const visible = tasks.slice(0, 6);
	return (
		<>
			<Box marginBottom={1}>
				<Text color={theme.colors.primary} bold>{theme.icons.chevron} Tasks</Text>
			</Box>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.muted} paddingX={1} marginBottom={1}>
				{visible.length === 0 ? (
					<Text dimColor>(none)</Text>
				) : (
					visible.map((task) => (
						<Box key={task.id} flexDirection="column" marginBottom={1}>
							<Text>
								<Text color={theme.colors.accent}>{task.id}</Text>
								<Text dimColor> [{task.status}] </Text>
								<Text>{task.description}</Text>
							</Text>
							<Text dimColor>
								type={task.type} progress={task.metadata.progress ?? '-'} note={task.metadata.status_note ?? '-'}
							</Text>
						</Box>
					))
				)}
			</Box>
		</>
	);
}

/**
 * MCP 服务器面板组件
 *
 * 显示已连接的 MCP 服务器列表。
 */
function McpPanel({servers, theme}: {servers: McpServerSnapshot[]; theme: ThemeConfig}): React.JSX.Element {
	return (
		<>
			<Box marginBottom={1}>
				<Text color={theme.colors.primary} bold>{theme.icons.chevron} MCP</Text>
			</Box>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.muted} paddingX={1} marginBottom={1}>
				{servers.length === 0 ? (
					<Text dimColor>(none)</Text>
				) : (
					servers.slice(0, 5).map((server) => (
						<Box key={server.name} flexDirection="column" marginBottom={1}>
							<Text>
								<Text color={theme.colors.accent}>{server.name}</Text>
								<Text dimColor> [{server.state}] </Text>
								<Text>{server.transport ?? 'unknown'}</Text>
							</Text>
							<Text dimColor>
								auth={String(Boolean(server.auth_configured))} tools={String(server.tool_count ?? 0)} resources=
								{String(server.resource_count ?? 0)}
							</Text>
							{server.detail ? <Text dimColor>{server.detail}</Text> : null}
						</Box>
					))
				)}
			</Box>
		</>
	);
}

/**
 * 命令面板组件
 *
 * 显示可用的命令列表和当前命令提示。
 */
function CommandPanel({
	commands,
	hints,
	theme,
}: {
	commands: string[];
	hints: string[];
	theme: ThemeConfig;
}): React.JSX.Element {
	return (
		<>
			<Box marginBottom={1}>
				<Text color={theme.colors.primary} bold>{theme.icons.chevron} Commands</Text>
			</Box>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.muted} paddingX={1}>
				{hints.length > 0 ? (
					hints.map((command, index) => (
						<Text key={command} color={index === 0 ? theme.colors.accent : theme.colors.text}>
							{command}
							{index === 0 ? <Text dimColor>  [tab]</Text> : ''}
						</Text>
					))
				) : commands.length > 0 ? (
					<Text dimColor>type / for commands</Text>
				) : (
					<Text dimColor>(none)</Text>
				)}
			</Box>
		</>
	);
}
