/**
 * @fileoverview 页脚组件
 *
 * 显示应用状态信息的页脚栏，包括：
 * - 当前使用的模型和提供商
 * - 认证状态和权限模式
 * - 任务数量
 * - MCP 服务器连接状态
 * - 桥接会话数量
 * - 当前语言和思考强度
 *
 * @module Footer
 */

import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

/**
 * 页脚组件
 *
 * 在终端底部显示当前会话的状态信息。
 *
 * @param props - 组件属性
 * @param props.status - 后端状态对象
 * @param props.taskCount - 当前任务数量
 * @returns 返回页脚的 JSX 元素
 */
export function Footer({status, taskCount}: {status: Record<string, unknown>; taskCount: number}): React.JSX.Element {
	const theme = useTheme();

	return (
		<Box marginTop={1} borderStyle="single" borderColor={theme.colors.muted} paddingX={1}>
			<Text dimColor>
				<Text color={theme.colors.primary}>model</Text>={String(status.model ?? 'unknown')}{' '}
				<Text color={theme.colors.primary}>provider</Text>={String(status.provider ?? 'unknown')}{' '}
				<Text color={theme.colors.primary}>auth</Text>={String(status.auth_status ?? 'unknown')}{' '}
				<Text color={theme.colors.primary}>permission</Text>={String(status.permission_mode ?? 'unknown')}{' '}
				<Text color={theme.colors.primary}>tasks</Text>={String(taskCount)}{' '}
				<Text color={theme.colors.primary}>mcp</Text>={String(status.mcp_connected ?? 0)}/{String(status.mcp_failed ?? 0)}{' '}
				<Text color={theme.colors.primary}>bridge</Text>={String(status.bridge_sessions ?? 0)}{' '}
				<Text color={theme.colors.primary}>language</Text>={String(status.ui_language ?? 'zh-CN')}{' '}
				<Text color={theme.colors.primary}>effort</Text>={String(status.effort ?? 'medium')}
			</Text>
		</Box>
	);
}
