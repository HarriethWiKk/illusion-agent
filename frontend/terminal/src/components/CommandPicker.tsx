import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

const MAX_VISIBLE = 6;

type CommandPickerMode = 'hints' | 'result';

type CommandPickerProps = {
	hints?: string[];
	selectedIndex?: number;
	totalCommands?: number;
	/** 结果模式：显示指令执行结果 */
	mode?: CommandPickerMode;
	result?: string;
	resultType?: 'success' | 'error' | 'info';
};

export function CommandPicker({
	hints,
	selectedIndex,
	mode = 'hints',
	result,
	resultType = 'info',
}: CommandPickerProps): React.JSX.Element | null {
	const theme = useTheme();

	// 结果模式：显示指令执行结果
	if (mode === 'result' && result) {
		const colorMap = {
			success: theme.colors.success,
			error: theme.colors.error,
			info: theme.colors.info,
		};
		const iconMap = {
			success: theme.icons.success,
			error: theme.icons.error,
			info: theme.icons.system,
		};
		const lines = result.split('\n');
		const truncated = lines.length > MAX_VISIBLE;
		const displayLines = truncated ? lines.slice(0, MAX_VISIBLE) : lines;
		return (
			<Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={colorMap[resultType]} paddingX={1}>
				{displayLines.map((line, i) => (
					<Text key={i} color={colorMap[resultType]}>
						{i === 0 ? `${iconMap[resultType]} ` : '  '}{line}
					</Text>
				))}
				{truncated ? (
					<Text color={colorMap[resultType]} dimColor>{'  '}&hellip; +{lines.length - MAX_VISIBLE} lines</Text>
				) : null}
				<Box marginTop={0}>
					<Text dimColor>
						<Text color={theme.colors.muted}>esc</Text> dismiss
					</Text>
				</Box>
			</Box>
		);
	}

	// 提示模式：显示命令提示列表
	if (!hints || hints.length === 0) {
		return null;
	}

	const safeSelectedIndex = selectedIndex ?? 0;
	const startIndex = Math.max(
		0,
		Math.min(
			safeSelectedIndex - Math.floor(MAX_VISIBLE / 2),
			hints.length - MAX_VISIBLE,
		),
	);
	const endIndex = Math.min(startIndex + MAX_VISIBLE, hints.length);
	const visible = hints.slice(startIndex, endIndex);

	return (
		<Box flexDirection="column" marginTop={1}>
			{visible.map((hint, vi) => {
				const actualIndex = startIndex + vi;
				const isSelected = actualIndex === safeSelectedIndex;
				return (
					<Box key={hint}>
						<Text color={isSelected ? theme.colors.suggestion : theme.colors.muted}>
							{isSelected ? `${theme.icons.pointer} ` : '  '}
						</Text>
						<Text color={isSelected ? theme.colors.suggestion : undefined} bold={isSelected} dimColor={!isSelected}>
							{hint}
						</Text>
						{isSelected ? <Text dimColor>{' [enter]'}</Text> : null}
					</Box>
				);
			})}
			<Box marginTop={0}>
				<Text dimColor>
					<Text color={theme.colors.muted}>↑↓</Text> navigate
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>↵</Text> select
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>tab</Text> complete
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>esc</Text> dismiss
				</Text>
			</Box>
		</Box>
	);
}
