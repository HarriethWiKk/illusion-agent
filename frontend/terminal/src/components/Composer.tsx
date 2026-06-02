/**
 * @fileoverview 输入编辑器组件
 *
 * 提供用户文本输入界面，支持：
 * - 输入内容清理（合并换行和多余空格）
 * - 忙碌/就绪状态显示
 * - 历史记录导航（ctrl-p/ctrl-n）
 *
 * @module Composer
 */

import React from 'react';
import {Box, Text} from 'ink';
import TextInput from 'ink-text-input';

import {useTheme} from '../theme/ThemeContext.js';

/**
 * 清理用户输入
 *
 * 将输入中的换行符替换为空格，合并连续空格，并去除首尾空格。
 *
 * @param value - 原始输入字符串
 * @returns 清理后的字符串
 */
function sanitizeInput(value: string): string {
	return value
		.replace(/[\r\n]+/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();
}

/**
 * 输入编辑器组件
 *
 * 提供带状态指示的文本输入框，支持历史记录导航。
 *
 * @param props - 组件属性
 * @param props.busy - 是否处于忙碌状态
 * @param props.input - 当前输入内容
 * @param props.setInput - 输入内容变更回调
 * @param props.onSubmit - 提交回调
 * @param props.historyIndex - 历史记录索引
 * @returns 返回输入编辑器的 JSX 元素
 */
export function Composer({
	busy,
	input,
	setInput,
	onSubmit,
	historyIndex,
}: {
	busy: boolean;
	input: string;
	setInput: (value: string) => void;
	onSubmit: (value: string) => void;
	historyIndex: number;
}): React.JSX.Element {
	const theme = useTheme();

	return (
		<Box flexDirection="column" marginTop={1}>
			<Box borderStyle="round" borderColor={busy ? theme.colors.warning : theme.colors.success} paddingX={1}>
				<Text color={busy ? theme.colors.warning : theme.colors.success} bold>
					{busy ? theme.icons.inProgress : theme.icons.completed}{' '}
				</Text>
				<Text color={busy ? theme.colors.warning : theme.colors.success} bold>
					{busy ? 'busy' : 'ready'}
				</Text>
				<Text> </Text>
				<TextInput
					value={input}
					onChange={(value) => setInput(sanitizeInput(value))}
					onSubmit={onSubmit}
				/>
			</Box>
			<Box marginTop={1}>
				<Text dimColor>
					<Text color={theme.colors.muted}>enter</Text>=submit{' '}
					<Text color={theme.colors.muted}>tab</Text>=complete{' '}
					<Text color={theme.colors.muted}>ctrl-p/ctrl-n</Text>=history{' '}
					<Text color={theme.colors.muted}>history_index</Text>={String(historyIndex)}
				</Text>
			</Box>
		</Box>
	);
}
