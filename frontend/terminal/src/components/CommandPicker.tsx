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
}: CommandPickerProps): React.JSX.Element | null {
	const theme = useTheme();

	// 结果模式：显示指令执行结果
	if (mode === 'result' && result) {
		const lines = result.split('\n');
		const displayLines = lines.slice(0, MAX_VISIBLE);

		return (
			<Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={theme.colors.illusion} paddingX={1}>
				{displayLines.map((line, i) => (
					<Text key={i} color={theme.colors.illusion}>{line}</Text>
				))}
				{lines.length > MAX_VISIBLE ? (
					<Text color={theme.colors.illusion} dimColor>
						{'  '}... +{lines.length - MAX_VISIBLE} more lines
					</Text>
				) : null}
				<Text dimColor>
					<Text color={theme.colors.muted}>esc</Text> dismiss
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>ctrl+o</Text> show full
				</Text>
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
