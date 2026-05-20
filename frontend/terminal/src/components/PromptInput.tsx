import React from 'react';
import {Box} from 'ink';

import type {UiLanguage} from '../i18n.js';
import {t} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';
import {Spinner} from './Spinner.js';
import MultilineTextInput from './MultilineTextInput.js';
import type {TodoItemSnapshot} from '../types.js';

function noop(): void {}

function sanitizeInput(value: string): string {
	// 仅移除回车符，保留换行符（多行）和空格
	return value.replace(/\r/g, '');
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
