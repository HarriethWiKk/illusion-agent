/**
 * @fileoverview 提示输入组件
 *
 * 终端前端的用户输入组件，包含：
 * - 加载动画（忙碌时显示）
 * - 多行文本输入框
 * - 输入内容清理（移除回车符）
 * - 占位符提示
 *
 * @module PromptInput
 */

import React from 'react';
import {Box} from 'ink';

import type {UiLanguage} from '../i18n.js';
import {t} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';
import MultilineTextInput from './MultilineTextInput.js';
import type {TodoItemSnapshot} from '../types.js';

/** 空操作函数，用于禁用提交 */
function noop(): void {}

/**
 * 清理输入内容
 *
 * 仅移除回车符，保留换行符（多行）和空格。
 *
 * @param value - 原始输入
 * @returns 清理后的输入
 */
function sanitizeInput(value: string): string {
	// 仅移除回车符，保留换行符（多行）和空格
	return value.replace(/\r/g, '');
}

/**
 * 提示输入组件
 *
 * 终端前端的用户输入组件。
 *
 * @param props - 组件属性
 * @param props.busy - 是否忙碌
 * @param props.input - 当前输入内容
 * @param props.setInput - 设置输入内容的回调
 * @param props.onSubmit - 提交回调
 * @param props.toolName - 当前工具名称（可选，用于加载动画显示）
 * @param props.suppressSubmit - 是否禁用提交（可选，用于命令选择器打开时）
 * @param props.cursorReset - 光标重置计数器（可选，用于重置光标位置）
 * @param props.language - 当前 UI 语言
 * @param props.todoItems - 待办事项列表（可选，用于加载动画显示）
 * @returns 返回提示输入的 JSX 元素
 */
export function PromptInput({
	busy,
	input,
	setInput,
	onSubmit,
	toolName,
	suppressSubmit,
	cursorReset,
	language,
	todoItems,
}: {
	busy: boolean;
	input: string;
	setInput: (value: string) => void;
	onSubmit: (value: string) => void;
	toolName?: string;
	suppressSubmit?: boolean;
	cursorReset?: number;
	language: UiLanguage;
	todoItems?: TodoItemSnapshot[];
}): React.JSX.Element {
	const theme = useTheme();

	const handleChange = React.useCallback((value: string) => {
		setInput(sanitizeInput(value));
	}, [setInput]);

	return (
		<Box flexDirection="column" marginTop={1}>
			{busy ? (
				<Box marginBottom={1}>
					<Spinner todoItems={todoItems} language={language} toolName={toolName} />
				</Box>
			) : null}
			<Box borderStyle="round" borderColor={theme.colors.promptBorder} paddingLeft={1} paddingRight={1}>
				<MultilineTextInput
					key={cursorReset ?? 0}
					value={input}
					onChange={handleChange}
					onSubmit={suppressSubmit ? noop : onSubmit}
					placeholder={t(language, 'longTextHint')}
					focus={!busy}
				/>
			</Box>
		</Box>
	);
}
