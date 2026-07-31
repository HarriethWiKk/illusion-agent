/**
 * @fileoverview 侧问（btw）单行输入框
 *
 * 在 busy 模式下由 Ctrl+B 触发，用于在不中断主任务的情况下
 * 向助手提出一个简短的侧问。Enter 提交，Esc 取消。
 *
 * @module BtwInlineInput
 */

import React, {useState} from 'react';
import {Box, Text, useInput} from 'ink';
import TextInput from 'ink-text-input';

import {useTheme} from '../theme/ThemeContext.js';
import {t, UiLanguage} from '../i18n.js';

/**
 * 侧问单行输入框属性
 */
interface BtwInlineInputProps {
	/** 当前 UI 语言 */
	language: UiLanguage;
	/** 提交回调，参数为非空的问题文本 */
	onSubmit: (question: string) => void;
	/** 取消回调（Esc 触发） */
	onCancel: () => void;
}

/**
 * 侧问单行输入框组件
 *
 * @param props - 组件属性
 * @returns 返回输入框的 JSX 元素
 */
export function BtwInlineInput({language, onSubmit, onCancel}: BtwInlineInputProps): React.JSX.Element {
	const theme = useTheme();
	const [value, setValue] = useState('');

	useInput((_input, key) => {
		if (key.escape) {
			onCancel();
			return;
		}
	});

	return (
		<Box>
			<Text color={theme.colors.illusion}>│ &gt; </Text>
			<TextInput
				value={value}
				onChange={setValue}
				placeholder={t(language, 'btwPlaceholder')}
				focus={true}
				showCursor={true}
				onSubmit={(v) => {
					const s = v.trim();
					if (s) {
						onSubmit(s);
					}
				}}
			/>
		</Box>
	);
}
