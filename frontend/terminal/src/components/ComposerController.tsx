/**
 * @fileoverview 输入编辑器控制器组件
 *
 * 管理输入状态、命令提示和键盘交互的高级控制器组件。
 * 封装了命令提示列表的显示逻辑和键盘导航。
 *
 * @module ComposerController
 */

import React, {useEffect, useMemo, useState} from 'react';
import {useInput} from 'ink';

import type {UiLanguage} from '../i18n.js';
import type {TodoItemSnapshot} from '../types.js';
import {CommandPicker} from './CommandPicker.js';
import {PromptInput} from './PromptInput.js';

/**
 * 输入编辑器控制器组件
 *
 * 作为输入区域的控制器，负责：
 * - 管理输入状态和命令提示
 * - 处理键盘导航（上下箭头、Tab 补全、Enter 选择、Esc 关闭）
 * - 协调命令选择器和输入框的显示
 *
 * @param props - 组件属性
 * @param props.commands - 可用命令列表
 * @param props.busy - 后端是否忙碌
 * @param props.disabled - 是否禁用输入
 * @param props.language - 当前 UI 语言
 * @param props.todoItems - 待办事项列表
 * @param props.toolName - 当前工具名称（可选）
 * @param props.onSubmit - 提交回调函数
 * @returns 返回输入编辑器控制器的 JSX 元素，如果禁用或忙碌则返回 null
 */
export function ComposerController({
	commands,
	busy,
	disabled,
	language,
	todoItems,
	toolName,
	onSubmit,
}: {
	commands: string[];
	busy: boolean;
	disabled: boolean;
	language: UiLanguage;
	todoItems: TodoItemSnapshot[];
	toolName?: string;
	onSubmit: (value: string) => void;
}): React.JSX.Element | null {
	const [input, setInput] = useState('');
	const [pickerIndex, setPickerIndex] = useState(0);
	const [localBusy, setLocalBusy] = useState(false);

	const commandHints = useMemo(() => {
		if (!input.startsWith('/')) {
			return [] as string[];
		}
		const value = input.trimEnd();
		if (!value) {
			return [] as string[];
		}
		const matches = commands.filter((cmd) => cmd.startsWith(value));
		if (value === '/') {
			const preferred = ['/language'];
			const boosted = preferred.filter((cmd) => matches.includes(cmd));
			const rest = matches.filter((cmd) => !preferred.includes(cmd));
			return [...boosted, ...rest];
		}
		return matches;
	}, [commands, input]);

	const showPicker = !disabled && input.startsWith('/') && commandHints.length > 0;
    const effectiveBusy = busy || localBusy;

	useEffect(() => {
		setPickerIndex(0);
	}, [showPicker, commandHints.length, input]);

	useEffect(() => {
		if (!busy) {
			setLocalBusy(false);
		}
	}, [busy]);

	useInput((chunk, key) => {
		if (disabled) {
			return;
		}

		if (showPicker) {
			if (key.upArrow) {
				setPickerIndex((i) => Math.max(0, i - 1));
				return;
			}
			if (key.downArrow) {
				setPickerIndex((i) => Math.min(commandHints.length - 1, i + 1));
				return;
			}
			if (key.return) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setLocalBusy(true);
					setInput('');
					onSubmit(selected);
				}
				return;
			}
			if (key.tab) {
				const selected = commandHints[pickerIndex];
				if (selected) {
					setInput(selected + ' ');
				}
				return;
			}
			if (key.escape) {
				setInput('');
				return;
			}
		}

		if (!showPicker && (key.upArrow || key.downArrow)) {
			return;
		}
	});

	if (disabled || effectiveBusy) {
		return null;
	}

	return (
		<>
			{showPicker ? <CommandPicker hints={commandHints} selectedIndex={pickerIndex} totalCommands={commands.length} /> : null}
			<PromptInput
				busy={effectiveBusy}
				input={input}
				setInput={setInput}
				onSubmit={(value) => {
					if (!value.trim() || disabled) {
						return;
					}
					setLocalBusy(true);
					onSubmit(value);
					setInput('');
				}}
				toolName={toolName}
				suppressSubmit={showPicker}
				language={language}
				todoItems={todoItems}
			/>
		</>
	);
}
