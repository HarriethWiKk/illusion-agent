/**
 * @fileoverview Goal 目标编辑框组件
 *
 * Ctrl+G → e 打开的行内多行编辑器（占据 busy 区，替换 Shimmer/Goal 状态行）：
 * - 基于 Cursor/MeasuredText 的多行编辑（wrap 行感知，长文本换行不乱）
 * - 视口最多显示 5 行，上下箭头移动光标时视口跟随滚动（超出部分可见）
 * - Enter 提交、Esc 取消；空目标不提交
 *
 * @module GoalEditBox
 */

import React, {useState} from 'react';
import {Box, Text, useInput} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import {useTerminalSize} from '../hooks/useTerminalSize.js';
import {t, UiLanguage} from '../i18n.js';
import MultilineTextInput from './MultilineTextInput.js';

/** 编辑框视口最大可见行数（超出部分随光标上下滚动） */
const MAX_VISIBLE_LINES = 5;

/**
 * Goal 目标编辑框组件
 *
 * @param props - 组件属性
 * @param props.initialValue - 初始目标文本（预填当前 objective）
 * @param props.language - 当前 UI 语言
 * @param props.onSubmit - 提交回调（参数为修剪后的目标文本，空文本不触发）
 * @param props.onCancel - 取消回调
 * @returns 返回编辑框的 JSX 元素
 */
export function GoalEditBox({
	initialValue,
	language,
	onSubmit,
	onCancel,
}: {
	initialValue: string;
	language: UiLanguage;
	onSubmit: (value: string) => void;
	onCancel: () => void;
}): React.JSX.Element {
	const theme = useTheme();
	const {columns} = useTerminalSize();
	const [value, setValue] = useState(initialValue);

	// Esc 取消（Enter 提交由 MultilineTextInput 的 onSubmit 处理）
	useInput((_chunk, key) => {
		if (key.escape) {
			onCancel();
		}
	});

	// 四边圆角框：边框2列 + padding 2列 + 光标预留1列 + 安全余量1列 = 6列
	const inputColumns = Math.max(10, columns - 6);

	return (
		<Box flexDirection="column" marginTop={1}>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.promptBorder} paddingLeft={1} paddingRight={1}>
				<Text color={theme.colors.illusionShimmer} bold>
					{t(language, 'goalEditPrompt')}
				</Text>
				<MultilineTextInput
					value={value}
					onChange={setValue}
					onSubmit={(v) => {
						const trimmed = v.trim();
						// 空目标不提交（保持编辑态）
						if (trimmed) {
							onSubmit(trimmed);
						}
					}}
					columns={inputColumns}
					maxVisibleLines={MAX_VISIBLE_LINES}
					focus={true}
				/>
			</Box>
		</Box>
	);
}
