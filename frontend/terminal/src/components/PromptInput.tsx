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
	// 由于 React effect 提交顺序（子组件先于父组件），ink-text-input 的 useInput
	// 比 PromptInput 的先注册，导致 Ctrl+U 时 ink-text-input 先插入 'u' 再触发 onChange，
	// 此时 shouldClearRef 尚未设置。直接调用 setInput 并利用 React 18 批处理，
	// 确保 setInput('') 覆盖 onChange 中的 setInput(valueWithU)。
	useInput((chunk, key) => {
		if (key.ctrl && chunk.toLowerCase() === 'u') {
			shouldClearRef.current = true;
			setInput('');
			// 微任务中重置标记，防止残留 flag 导致下次正常输入被误清空
			Promise.resolve().then(() => { shouldClearRef.current = false; });
		}
		if (key.ctrl && chunk.toLowerCase() === 'o') {
			suppressNextChangeRef.current = true;
			setInput(inputRef.current);
			Promise.resolve().then(() => { suppressNextChangeRef.current = false; });
		}
	}, {isActive: !busy});

	// 处理 onChange，拦截 Ctrl+U/Ctrl+O 产生的多余字符
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
