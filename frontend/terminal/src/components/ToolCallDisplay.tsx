/**
 * @fileoverview 工具调用显示组件
 *
 * 独立的工具调用和结果渲染组件，用于 TranscriptPane 等场景。
 * 使用 ToolRegistry 获取工具专用渲染器。
 *
 * @module ToolCallDisplay
 */

import React from 'react';
import {Box, Text} from 'ink';
import type {ThemeConfig} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';
import {getTool} from '../tools/registry.js';
import {stringWidth, wrapText} from '../utils/markdown.js';

/** 最小换行宽度 */
const MIN_WRAP_WIDTH = 12;
/** 宽度安全余量 */
const WIDTH_SAFETY_EXTRA = 2;

/**
 * 工具调用消息组件
 *
 * 显示工具图标、名称和参数摘要。
 *
 * @param item - 工具调用的转录项
 * @param theme - 主题配置
 * @param availableWidth - 可用显示宽度
 * @returns 工具调用显示的 JSX 元素
 */
export function ToolUseMessage({
	item,
	theme,
	availableWidth,
}: {
	item: TranscriptItem;
	theme: ThemeConfig;
	availableWidth?: number;
}): React.JSX.Element {
	const toolName = item.tool_name ?? 'tool';
	const tool = getTool(toolName);
	const displayName = tool.displayName(item.tool_input) || toolName;
	const summary = tool.renderToolUseMessage(item.tool_input);
	const content = summary ? `${displayName}(${summary})` : displayName;

	const prefix = `${theme.icons.tool} `;
	const prefixWidth = stringWidth(prefix);
	const maxWidth = availableWidth
		? Math.max(MIN_WRAP_WIDTH, availableWidth - prefixWidth - WIDTH_SAFETY_EXTRA)
		: undefined;

	// 自动换行处理
	const lines = maxWidth
		? wrapText(content, maxWidth, {hard: true})
		: [content];

	return (
		<Box flexDirection="column">
			{lines.map((line, i) => (
				<Box key={i}>
					{i === 0 ? (
						<Text>
							<Text color={theme.colors.info}>{prefix}</Text>
							<Text bold>{line}</Text>
						</Text>
					) : (
						<Text bold>{' '.repeat(prefixWidth)}{line}</Text>
					)}
				</Box>
			))}
		</Box>
	);
}

/**
 * 工具结果消息组件
 *
 * 显示结果前缀、状态图标和结果内容。
 *
 * @param item - 工具结果的转录项
 * @param theme - 主题配置
 * @returns 工具结果显示的 JSX 元素
 */
export function ToolResultMessage({
	item,
	theme,
}: {
	item: TranscriptItem;
	theme: ThemeConfig;
}): React.JSX.Element {
	const toolName = item.tool_name ?? 'tool';
	const tool = getTool(toolName);
	const isError = item.is_error;
	const icon = isError ? theme.icons.cross : theme.icons.check;
	const iconColor = isError ? theme.colors.error : theme.colors.success;

	const rendered = tool.renderToolResultMessage(
		item.text,
		item.tool_input,
		false,
		item.structured_output,
	);

	return (
		<Box flexDirection="column">
			<Box>
				<Text dimColor>{`  ${theme.icons.resultPrefix} `}</Text>
				<Text color={iconColor}>{icon} </Text>
			</Box>
			<Box marginLeft={2}>
				{rendered}
			</Box>
		</Box>
	);
}
