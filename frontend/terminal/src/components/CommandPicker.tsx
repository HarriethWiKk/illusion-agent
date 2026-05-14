import React, {useEffect, useState} from 'react';
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
	/** 自动放映完成后的回调 */
	onPlaybackComplete?: () => void;
};

export function CommandPicker({
	hints,
	selectedIndex,
	mode = 'hints',
	result,
	resultType = 'info',
	onPlaybackComplete,
}: CommandPickerProps): React.JSX.Element | null {
	const theme = useTheme();

	// Hooks 必须在顶层调用（不能放在条件分支内）
	const lines = mode === 'result' && result ? result.split('\n') : [];
	const needsPlayback = lines.length > MAX_VISIBLE;
	const [playbackIndex, setPlaybackIndex] = useState(0);

	// 自动放映：每 500ms 滚动一行，放映完成后通知父组件清除
	useEffect(() => {
		if (!needsPlayback) return;
		const timer = setInterval(() => {
			setPlaybackIndex((prev) => {
				if (prev >= lines.length - MAX_VISIBLE) {
					clearInterval(timer);
					onPlaybackComplete?.();
					return prev;
				}
				return prev + 1;
			});
		}, 500);
		return () => clearInterval(timer);
	}, [needsPlayback, lines.length]);

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
		const visibleLines = needsPlayback
			? lines.slice(playbackIndex, playbackIndex + MAX_VISIBLE)
			: lines;

		return (
			<Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={colorMap[resultType]} paddingX={1}>
				{visibleLines.map((line, i) => (
					<Text key={needsPlayback ? playbackIndex + i : i} color={colorMap[resultType]}>
						{i === 0 ? <Text color={theme.colors.illusion}>{iconMap[resultType]}{' '}</Text> : '  '}{line}
					</Text>
				))}
				{needsPlayback ? (
					<Text color={colorMap[resultType]} dimColor>{'  '}{'…'} {playbackIndex + MAX_VISIBLE}/{lines.length}</Text>
				) : null}
				<Text dimColor>
					<Text color={theme.colors.muted}>esc</Text> dismiss
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
