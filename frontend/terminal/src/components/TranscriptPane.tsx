/**
 * @fileoverview 转录面板组件
 *
 * 显示对话历史的简化视图，用于侧边面板中。
 * 显示最近的消息项和当前助手回复缓冲区。
 *
 * @module TranscriptPane
 */

import React from 'react';
import {Box, Text} from 'ink';

import type {ThemeConfig} from '../theme/ThemeContext.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';

/** 最大可见消息项数 */
const MAX_VISIBLE_ITEMS = 30;

/**
 * 转录面板组件
 *
 * 显示对话历史的简化视图。
 *
 * @param props - 组件属性
 * @param props.items - 转录项列表
 * @param props.assistantBuffer - 助手回复缓冲区
 * @returns 返回转录面板的 JSX 元素
 */
export function TranscriptPane({
	items,
	assistantBuffer,
}: {
	items: TranscriptItem[];
	assistantBuffer: string;
}): React.JSX.Element {
	const theme = useTheme();
	const visible = items.slice(-MAX_VISIBLE_ITEMS);

	return (
		<Box flexDirection="column" width="68%" paddingRight={1}>
			<Box marginBottom={1}>
				<Text color={theme.colors.primary} bold>{theme.icons.chevron} Transcript</Text>
			</Box>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.muted} paddingX={1} minHeight={24}>
				{visible.map((item, index) => (
					<Box key={`${index}-${item.role}`} flexDirection="row">
						<Text color={roleColor(item.role, theme)} bold>
							{labelFor(item.role, theme)}{' '}
						</Text>
						<Text color={roleColor(item.role, theme)}>{item.text}</Text>
					</Box>
				))}
				{assistantBuffer ? (
					<Box flexDirection="row">
						<Text color={theme.colors.success} bold>{theme.icons.assistant} </Text>
						<Text color={theme.colors.success}>{assistantBuffer}</Text>
					</Box>
				) : null}
			</Box>
		</Box>
	);
}

function labelFor(role: TranscriptItem['role'], theme: ThemeConfig): string {
	switch (role) {
		case 'user':
			return theme.icons.user;
		case 'assistant':
			return theme.icons.assistant;
		case 'tool':
			return theme.icons.tool;
		case 'tool_result':
			return theme.icons.check;
		case 'system':
			return theme.icons.system;
		case 'log':
			return theme.icons.bullet;
		default:
			return theme.icons.dot;
	}
}

function roleColor(role: TranscriptItem['role'], theme: ThemeConfig): string {
	switch (role) {
		case 'assistant':
			return theme.colors.success;
		case 'tool':
			return theme.colors.accent;
		case 'tool_result':
			return theme.colors.warning;
		case 'system':
			return theme.colors.info;
		case 'log':
			return theme.colors.muted;
		default:
			return theme.colors.text;
	}
}
