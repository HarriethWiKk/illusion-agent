/**
 * @fileoverview 问答预览框组件
 *
 * 用于 ask_user_question 工具单选问题的 preview 字段：以带边框的等宽框
 * 渲染纯文本预览内容。超过最大行数的内容支持 ctrl+←/→ 分页浏览。
 *
 * @module QuestionPreviewBox
 */

import React, {useMemo} from 'react';
import {Box, Text} from 'ink';

import {useTerminalSize} from '../hooks/useTerminalSize.js';
import {useTheme} from '../theme/ThemeContext.js';

/** 边框字符集 */
const BOX_CHARS = {
	topLeft: '┌',
	topRight: '┐',
	bottomLeft: '└',
	bottomRight: '┘',
	horizontal: '─',
	vertical: '│',
	teeLeft: '├',
	teeRight: '┤',
} as const;

/**
 * 预览框属性
 */
type Props = {
	/** 预览内容（Markdown） */
	content: string;
	/** 最大显示行数（超出截断），默认 10 */
	maxLines?: number;
	/** 框的最小宽度，默认 40 */
	minWidth?: number;
	/** 框的最大可用宽度（容器宽度限制） */
	maxWidth?: number;
	/** 起始行号（从 0 开始，用于分页），默认 0 */
	startLine?: number;
};

/**
 * 按视觉宽度计算字符串宽度（粗略，处理常见 CJK/全角字符）
 */
function visualWidth(str: string): number {
	let width = 0;
	for (const ch of str) {
		const code = ch.codePointAt(0) ?? 0;
		// 简易判定：CJK 区段按宽度 2 计
		if (
			(code >= 0x1100 && code <= 0x115f) ||
			(code >= 0x2e80 && code <= 0x303e) ||
			(code >= 0x3041 && code <= 0x33ff) ||
			(code >= 0x3400 && code <= 0x4dbf) ||
			(code >= 0x4e00 && code <= 0x9fff) ||
			(code >= 0xa000 && code <= 0xa4cf) ||
			(code >= 0xac00 && code <= 0xd7a3) ||
			(code >= 0xf900 && code <= 0xfaff) ||
			(code >= 0xfe30 && code <= 0xfe4f) ||
			(code >= 0xff00 && code <= 0xff60) ||
			(code >= 0xffe0 && code <= 0xffe6)
		) {
			width += 2;
		} else {
			width += 1;
		}
	}
	return width;
}

/**
 * 问答预览框组件
 *
 * @param props - 组件属性
 * @returns 带边框的预览框 JSX 元素
 */
export function QuestionPreviewBox({
	content,
	maxLines = 10,
	minWidth = 40,
	maxWidth,
	startLine = 0,
}: Props): React.JSX.Element {
	const theme = useTheme();
	const {columns: terminalWidth} = useTerminalSize();
	const effectiveMaxWidth = maxWidth ?? terminalWidth - 4;

	// 计算框宽：取内容最宽行与最小宽度的较大值，再加边框 padding，封顶于最大宽
	const contentLines = useMemo(() => content.split('\n'), [content]);
	const contentWidth = useMemo(
		() => Math.max(minWidth, ...contentLines.map((line) => visualWidth(line))),
		[contentLines, minWidth],
	);
	const boxWidth = Math.min(contentWidth + 4, effectiveMaxWidth);
	const innerWidth = Math.max(1, boxWidth - 4);

	// 截断处理：按 startLine 分页显示内容
	const totalLines = contentLines.length;
	const totalPages = Math.max(1, Math.ceil(totalLines / maxLines));
	const currentPage = Math.min(Math.floor(startLine / maxLines), totalPages - 1);
	const effectiveStart = currentPage * maxLines;
	const visibleLines = contentLines.slice(effectiveStart, effectiveStart + maxLines);
	const hasMultiplePages = totalPages > 1;

	const topBorder = `${BOX_CHARS.topLeft}${BOX_CHARS.horizontal.repeat(Math.max(0, boxWidth - 2))}${BOX_CHARS.topRight}`;
	const bottomBorder = `${BOX_CHARS.bottomLeft}${BOX_CHARS.horizontal.repeat(Math.max(0, boxWidth - 2))}${BOX_CHARS.bottomRight}`;
	// 页码指示行：├── Page 2/5 ── ctrl + ←/→ ──┤
	const pageLabel = `${BOX_CHARS.horizontal.repeat(2)} Page ${currentPage + 1}/${totalPages} ${BOX_CHARS.horizontal.repeat(2)} ctrl + \u2190/\u2192 `;
	const pageFill = Math.max(0, boxWidth - 2 - visualWidth(pageLabel));
	const pageBar = `${BOX_CHARS.teeLeft}${pageLabel}${BOX_CHARS.horizontal.repeat(pageFill)}${BOX_CHARS.teeRight}`;

	return (
		<Box flexDirection="column">
			<Text dimColor>{topBorder}</Text>
			{/* 预览内容区：纯文本渲染，不解析 Markdown */}
			<Box flexDirection="row">
				<Text dimColor>{BOX_CHARS.vertical} </Text>
				<Box flexDirection="column" width={innerWidth}>
					{content.trim() ? (
						visibleLines.map((line, i) => (
							<Text key={i}>{line}</Text>
						))
					) : (
						<Text dimColor>No preview available</Text>
					)}
				</Box>
				<Text dimColor> {BOX_CHARS.vertical}</Text>
			</Box>
			{hasMultiplePages ? <Text color={theme.colors.info}>{pageBar}</Text> : null}
			<Text dimColor>{bottomBorder}</Text>
		</Box>
	);
}
