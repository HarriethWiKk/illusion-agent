/**
 * @fileoverview 选择模态对话框组件
 *
 * 提供通用的选择列表界面，支持：
 * - 键盘上下导航
 * - 当前选项高亮
 * - 选项描述显示
 * - 活跃状态标记
 *
 * @module SelectModal
 */

import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

/**
 * 选择选项类型
 */
export type SelectOption = {
	/** 选项值 */
	value: string;
	/** 显示标签 */
	label: string;
	/** 选项描述（可选） */
	description?: string;
	/** 是否为当前活跃选项（可选） */
	active?: boolean;
};

/** 最大可见选项数 */
const MAX_VISIBLE = 6;

/**
 * 选择模态对话框组件
 *
 * 显示一个可导航的选择列表，用于权限模式选择、语言切换等场景。
 *
 * @param props - 组件属性
 * @param props.title - 对话框标题
 * @param props.options - 选项列表
 * @param props.selectedIndex - 当前选中的索引
 * @returns 返回选择模态对话框的 JSX 元素
 */
export function SelectModal({
	title,
	options,
	selectedIndex,
}: {
	title: string;
	options: SelectOption[];
	selectedIndex: number;
}): React.JSX.Element {
	const theme = useTheme();

	const startIndex = Math.max(
		0,
		Math.min(
			selectedIndex - Math.floor(MAX_VISIBLE / 2),
			options.length - MAX_VISIBLE,
		),
	);
	const endIndex = Math.min(startIndex + MAX_VISIBLE, options.length);
	const visible = options.slice(startIndex, endIndex);

	return (
		<Box flexDirection="column" marginTop={1}>
			<Box>
				<Text color={theme.colors.permission}>{theme.icons.pointer} </Text>
				<Text bold>{title}</Text>
			</Box>
			{visible.map((opt, vi) => {
				const i = startIndex + vi;
				const isSelected = i === selectedIndex;
				const isCurrent = opt.active;
				return (
					<Box key={opt.value}>
						<Text color={isSelected ? theme.colors.suggestion : theme.colors.muted}>
							{isSelected ? `${theme.icons.pointer} ` : '  '}
						</Text>
						<Text color={isSelected ? theme.colors.suggestion : undefined} bold={isSelected} dimColor={!isSelected}>
							{opt.label}
						</Text>
						{isCurrent ? (
							<Box marginLeft={1}>
								<Text color={theme.colors.success} dimColor>(current)</Text>
							</Box>
						) : null}
						{opt.description ? (
							<Box marginLeft={1}>
								<Text dimColor>{theme.icons.middleDot} {opt.description}</Text>
							</Box>
						) : null}
					</Box>
				);
			})}
			<Box>
				<Text dimColor>
					<Text color={theme.colors.muted}>↑↓</Text> navigate
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>↵</Text> select
					<Text> {theme.icons.middleDot} </Text>
					<Text color={theme.colors.muted}>esc</Text> cancel
				</Text>
			</Box>
		</Box>
	);
}
