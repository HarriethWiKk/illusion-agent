/**
 * @fileoverview 待办事项面板组件
 *
 * 显示当前任务的待办事项列表，支持：
 * - 任务状态显示（进行中、待处理、已完成）
 * - 自动排序（最近完成 > 进行中 > 待处理 > 较早完成）
 * - 所有任务完成后自动隐藏
 * - 最近完成任务的高亮显示
 *
 * @module TodoPanel
 */

import React, {useEffect, useRef, useState} from 'react';
import {Box, Text} from 'ink';

import type {ThemeConfig} from '../theme/ThemeContext.js';
import {useTheme} from '../theme/ThemeContext.js';
import {useTerminalSize} from '../hooks/useTerminalSize.js';
import type {TodoItemSnapshot} from '../types.js';
import {stringWidth, truncateToDisplayWidth, WIDTH_SAFETY_EXTRA} from '../utils/markdown.js';

/** 所有任务完成后自动隐藏的延迟时间（毫秒） */
const HIDE_DELAY_MS = 5000;

/** 最近完成任务的高亮时间（毫秒） */
const RECENT_COMPLETED_TTL_MS = 30_000;

/** 最大显示待办事项数量 */
const MAX_TODO_DISPLAY = 4;

/**
 * 待办事项面板组件
 *
 * 显示当前任务的待办事项列表。
 *
 * @param props - 组件属性
 * @param props.items - 待办事项列表
 * @returns 返回待办事项面板的 JSX 元素
 */
export function TodoPanel({items, externallyHidden}: {items: TodoItemSnapshot[]; externallyHidden?: boolean}): React.JSX.Element {
	const theme = useTheme();
	const {columns: terminalWidth} = useTerminalSize();
	const [hidden, setHidden] = useState(false);
	const hideTimerRef = useRef<NodeJS.Timeout | null>(null);
	const completionTimeRef = useRef<Record<string, number>>({});

	const completed = items.filter((t) => t.status === 'completed').length;
	const inProgress = items.filter((t) => t.status === 'in_progress').length;
	const allDone = completed === items.length && items.length > 0;

	// 跟踪任务完成时间
	const now = Date.now();
	for (const item of items) {
		if (item.status === 'completed' && !(item.content in completionTimeRef.current)) {
			completionTimeRef.current[item.content] = now;
		}
	}

	// 所有任务完成后延迟隐藏（必须在所有条件 return 之前，遵守 Hooks 规则）
	useEffect(() => {
		if (allDone) {
			if (hideTimerRef.current === null) {
				hideTimerRef.current = setTimeout(() => {
					setHidden(true);
					hideTimerRef.current = null;
				}, HIDE_DELAY_MS);
			}
		} else {
			setHidden(false);
			if (hideTimerRef.current !== null) {
				clearTimeout(hideTimerRef.current);
				hideTimerRef.current = null;
			}
		}
		return () => {
			if (hideTimerRef.current !== null) {
				clearTimeout(hideTimerRef.current);
				hideTimerRef.current = null;
			}
		};
	}, [allDone]);

	// 条件 return 放在 useEffect 之后，避免违反 React Hooks 规则
	if (items.length === 0 || hidden || externallyHidden) {
		return <></>;
	}

	// 排序：最近完成 > in_progress > pending > 较早完成
	const sorted = [...items].sort((a, b) => {
		const aRecent = a.status === 'completed' && (now - (completionTimeRef.current[a.content] ?? 0)) < RECENT_COMPLETED_TTL_MS;
		const bRecent = b.status === 'completed' && (now - (completionTimeRef.current[b.content] ?? 0)) < RECENT_COMPLETED_TTL_MS;
		const order = (item: TodoItemSnapshot, isRecent: boolean): number => {
			if (item.status === 'in_progress') return 0;
			if (isRecent) return 1;
			if (item.status === 'pending') return 2;
			return 3;
		};
		return order(a, aRecent) - order(b, bRecent);
	});

	const truncated = sorted.length > MAX_TODO_DISPLAY;
	const display = truncated ? sorted.slice(0, MAX_TODO_DISPLAY) : sorted;
	const remaining = sorted.length - MAX_TODO_DISPLAY;

	// 竖条 ▎ 1 字符 + 左 padding 1 + 右 padding 1 = 内容宽度需减 3
	const contentWidth = terminalWidth - 3;

	return (
		<Box flexDirection="column" marginTop={1}>
			<Box flexDirection="row">
				{/* 左侧 illusion 竖条：▎ 字符，每行一个，覆盖标题+任务+折叠提示行 */}
				<Box flexDirection="column">
					<Text color={theme.colors.illusion}>▎</Text>
					{display.map((_, i) => (
						<Text key={i} color={theme.colors.illusion}>▎</Text>
					))}
					{truncated ? <Text color={theme.colors.illusion}>▎</Text> : null}
				</Box>
				{/* 右侧内容区 */}
				<Box flexDirection="column" paddingLeft={1} flexGrow={1}>
					<Box marginBottom={0}>
						<Text inverse bold color={theme.colors.illusion}>{' Todo '}</Text>
						<Text dimColor>{`  ${completed}/${items.length} done`}</Text>
						{inProgress > 0 ? <Text color={theme.colors.info} bold>{`  ${inProgress} active`}</Text> : null}
					</Box>
					{display.map((item, i) => (
						<TodoRow key={i} item={item} theme={theme} now={now} completionTimes={completionTimeRef.current} contentWidth={contentWidth} />
					))}
					{truncated ? (
						<Box>
							<Text dimColor>{`  … +${remaining} more`}</Text>
						</Box>
					) : null}
				</Box>
			</Box>
		</Box>
	);
}

function TodoRow({item, theme, now, completionTimes, contentWidth}: {item: TodoItemSnapshot; theme: ThemeConfig; now: number; completionTimes: Record<string, number>; contentWidth: number}): React.JSX.Element {
	let icon: string;
	let color: string;

	switch (item.status) {
		case 'completed':
			icon = theme.icons.check;
			color = theme.colors.success;
			break;
		case 'in_progress':
			icon = theme.icons.inProgress;
			color = theme.colors.illusion;
			break;
		default:
			icon = theme.icons.pending;
			color = theme.colors.muted;
			break;
	}

	const isCompleted = item.status === 'completed';
	// 最近完成的任务不高亮（不dim）
	const isRecentCompleted = isCompleted && (now - (completionTimes[item.content] ?? 0)) < RECENT_COMPLETED_TTL_MS;

	// 前缀 = 图标 + 空格
	const prefixWidth = stringWidth(icon) + 1;
	const maxWidth = Math.max(12, contentWidth - prefixWidth - WIDTH_SAFETY_EXTRA);
	const displayContent = truncateToDisplayWidth(item.content, maxWidth);

	return (
		<Box>
			<Text color={color}>{icon} </Text>
			<Text
				color={isCompleted && !isRecentCompleted ? theme.colors.muted : undefined}
				dimColor={isCompleted && !isRecentCompleted}
				strikethrough={isCompleted}
				bold={item.status === 'in_progress'}
			>
				{displayContent}
			</Text>
		</Box>
	);
}
