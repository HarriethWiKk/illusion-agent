import React from 'react';
import {Box} from 'ink';
import TextInput from 'ink-text-input';

import type {UiLanguage} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';
import type {TodoItemSnapshot} from '../types.js';

function noop(): void {}

function sanitizeInput(value: string): string {
	// 将多行文本转为单行：换行符替换为空格，并清理多余空格
	return value
		.replace(/[\r\n]+/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();
}

export function PromptInput({
	busy,
	input,
	setInput,
	onSubmit,
	toolName,
	suppressSubmit,
	language,
	todoItems,
}: {
	busy: boolean;
	input: string;
	setInput: (value: string) => void;
	onSubmit: (value: string) => void;
	toolName?: string;
	suppressSubmit?: boolean;
	language: UiLanguage;
	todoItems?: TodoItemSnapshot[];
}): React.JSX.Element {
	const theme = useTheme();

	return (
		<Box flexDirection="column" marginTop={1}>
			{busy ? (
				<Box marginBottom={1}>
					<Spinner todoItems={todoItems} language={language} toolName={toolName} />
				</Box>
			) : null}
			<Box borderStyle="round" borderColor={theme.colors.promptBorder} paddingLeft={1} paddingRight={1}>
				<TextInput
					value={input}
					onChange={(value) => setInput(sanitizeInput(value))}
					onSubmit={suppressSubmit ? noop : onSubmit}
					focus={!busy}
				/>
			</Box>
		</Box>
	);
}
