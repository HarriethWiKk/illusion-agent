import React, {useRef, useCallback} from 'react';
import {Box, useInput} from 'ink';
import TextInput from 'ink-text-input';

import type {UiLanguage} from '../i18n.js';
import {t} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';
import type {TodoItemSnapshot} from '../types.js';

function noop(): void {}

function sanitizeInput(value: string): string {
	// 将多行文本转为单行：换行符替换为空格，并清理多余空格
	// 注意：不在输入阶段 trim，避免 ink-text-input 的 cursorOffset 与实际值不同步
	return value
		.replace(/[\r\n]+/g, ' ')
		.replace(/\s+/g, ' ');
}

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
	const shouldClearRef = useRef(false);
	const suppressNextChangeRef = useRef(false);
	const inputRef = useRef(input);
	inputRef.current = input;

	// Ctrl+U 清空输入框，Ctrl+O 阻止输入框捕获
	useInput((chunk, key) => {
		if (key.ctrl && chunk.toLowerCase() === 'u') {
			// 标记需要清空，onChange 会检测到并清空
			shouldClearRef.current = true;
		}
		if (key.ctrl && chunk.toLowerCase() === 'o') {
			// 标记需要抑制下一次 onChange，防止 'o' 出现在输入框
			suppressNextChangeRef.current = true;
		}
	}, {isActive: !busy});

	// 处理 onChange，拦截 Ctrl+U 导致的 'u' 输入和 Ctrl+O 导致的 'o' 输入
	const handleChange = useCallback((value: string) => {
		if (shouldClearRef.current) {
			shouldClearRef.current = false;
			setInput('');
			return;
		}
		if (suppressNextChangeRef.current) {
			suppressNextChangeRef.current = false;
			setInput(inputRef.current);
			return;
		}
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
				<TextInput
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
