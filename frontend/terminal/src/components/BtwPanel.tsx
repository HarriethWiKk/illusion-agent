/**
 * @fileoverview 侧问（btw）回复显示面板
 *
 * 在 busy 模式下展示助手对侧问的回复，特性：
 * - 竖杠（▎）作为左侧视觉前缀，每行一条
 * - 最多显示 5 行，超出部分通过上下箭头翻页
 * - 回复使用 suggestion 色，错误使用 error 色
 * - Esc 关闭面板
 *
 * @module BtwPanel
 */

import React, {useState} from 'react';
import {Box, Text, useInput} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import {useTerminalSize} from '../hooks/useTerminalSize.js';
import {t, UiLanguage} from '../i18n.js';
import {truncateToDisplayWidth, WIDTH_SAFETY_EXTRA} from '../utils/markdown.js';

/** 单次最多展示的回复行数 */
const MAX_LINES = 5;

/**
 * 侧问回复面板属性
 */
interface BtwPanelProps {
	/** 助手回复文本（多行），无回复时为 null */
	reply: string | null;
	/** 错误文本，无错误时为 null */
	error: string | null;
	/** 是否正在等待回复 */
	loading: boolean;
	/** 当前 UI 语言 */
	language: UiLanguage;
	/** 关闭面板回调（Esc 触发） */
	onDismiss: () => void;
}

/**
 * 侧问回复面板组件
 *
 * @param props - 组件属性
 * @returns 返回面板的 JSX 元素
 */
export function BtwPanel({reply, error, loading, language, onDismiss}: BtwPanelProps): React.JSX.Element {
	const theme = useTheme();
	const {columns: terminalWidth} = useTerminalSize();
	const [offset, setOffset] = useState(0);

	const text = reply ?? error ?? '';
	const lines = text.split('\n');
	const visibleLines = lines.slice(offset, offset + MAX_LINES);
	const hasMore = lines.length > MAX_LINES;

	// 前缀宽度：▎（1 列）+ 空格（1 列）= 2 列
	const contentWidth = Math.max(10, terminalWidth - 2 - WIDTH_SAFETY_EXTRA);

	useInput((_input, key) => {
		if (key.escape) {
			onDismiss();
			return;
		}
		if (key.upArrow) {
			setOffset((o) => Math.max(0, o - MAX_LINES));
			return;
		}
		if (key.downArrow) {
			setOffset((o) => Math.min(Math.max(0, lines.length - MAX_LINES), o + MAX_LINES));
			return;
		}
	});

	if (loading) {
		return (
			<Box>
				<Text color={theme.colors.suggestion}>▎ </Text>
				<Text color={theme.colors.suggestion}>{t(language, 'btwAnswering')}</Text>
			</Box>
		);
	}

	const lineColor = error ? theme.colors.error : theme.colors.suggestion;

	return (
		<Box flexDirection="column">
			{visibleLines.map((line, i) => (
				<Box key={i}>
					<Text color={lineColor}>▎ </Text>
					<Text color={lineColor}>{truncateToDisplayWidth(line, contentWidth)}</Text>
				</Box>
			))}
			{hasMore ? (
				<Box>
					<Text color={theme.colors.suggestion}>▎ </Text>
					<Text color={theme.colors.muted}>{`… (+${lines.length - offset - MAX_LINES} more lines, ↑/↓ ${t(language, 'questionHintNavigate')}, esc ${t(language, 'questionHintCancel')})`}</Text>
				</Box>
			) : null}
		</Box>
	);
}
