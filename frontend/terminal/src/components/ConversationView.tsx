import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Box, Static, Text} from 'ink';

import {useTerminalSize} from '../hooks/useTerminalSize.js';
import type {UiLanguage} from '../i18n.js';
import {t} from '../i18n.js';
import type {PendingToolCall} from '../types.js';
import type {ThemeConfig} from '../theme/ThemeContext.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {TranscriptItem} from '../types.js';
import {stringWidth, wrapText} from '../utils/markdown.js';
import {renderAssistantText, stripThinkTags, extractThinkContent, hasThinkTags, stripToolCallArtifacts, mergeReasoning} from '../utils/thinking.js';
import {MarkdownContent, renderInlineMarkdown} from './MarkdownContent.js';
import {WelcomeBanner} from './WelcomeBanner.js';

const MAX_RESULT_LINES = 2;
const MAX_COMMAND_LINES = 2;
const MAX_COMMAND_CHARS = 160;
const STREAMING_TAIL_LINES = 10;
const MIN_WRAP_WIDTH = 12;
const WIDTH_SAFETY_EXTRA = 2;

export function ConversationView({
	staticItems,
	clearCount,
	assistantBuffer,
	showWelcome,
	showThinking,
	language,
	pendingToolCall,
}: {
	staticItems: TranscriptItem[];
	clearCount: number;
	assistantBuffer: string;
	showWelcome: boolean;
	showThinking: boolean;
	language: UiLanguage;
	pendingToolCall?: PendingToolCall | null;
	commandPickerOpen?: boolean;
}): React.JSX.Element {
	const theme = useTheme();
	const {columns: terminalWidth} = useTerminalSize();
	const filtered = useMemo(() => staticItems.filter((item) => {
		if (!isEmptyItem(item)) {
			if (item.role === 'user' && item.text.startsWith('/')) {
				return false;
			}
			return true;
		}
		return false;
	}), [staticItems]);
	const grouped = useMemo(() => groupToolItems(filtered), [filtered]);
	const displayItems = useMemo<DisplayEntry[]>(() => {
		const entries: GroupEntry[] = showWelcome
			? [{type: 'welcome', role: 'welcome'}, ...grouped]
			: grouped;
		return entries.map((entry, index) => ({
			key: `s-${index}`,
			entry,
			prevRole: index > 0 ? entries[index - 1]?.role : undefined,
		}));
	}, [grouped, showWelcome]);
	const displayedBuffer = assistantBuffer; // Already processed in useBackendSession
	const isSuppressedByStatic = useMemo(() => {
		if (!displayedBuffer) return false;
		const lastAssistant = [...grouped].reverse().find((entry) => entry.role === 'assistant');
		if (!lastAssistant) return false;
		const item = lastAssistant.type === 'single' ? lastAssistant.item : null;
		if (!item) return false;
		const staticDisplayText = renderAssistantText(item.text, showThinking, item.reasoning);
		return isTextSubsetOrEqual(staticDisplayText, displayedBuffer);
	}, [grouped, displayedBuffer, showThinking]);

	return (
		<>
			<Static key={clearCount} items={displayItems}>
				{(display) => {
					const {entry, prevRole, key} = display;
					if (entry.type === 'welcome') {
						return <WelcomeBanner key={key} language={language} />;
					}
					if (entry.type === 'tool_group') {
						return <ToolGroupRow key={key} toolItem={entry.toolItem} resultItem={entry.resultItem} theme={theme} prevRole={prevRole} terminalWidth={terminalWidth} />;
					}
					return <MessageRow key={key} item={entry.item} theme={theme} language={language} prevRole={prevRole} showThinking={showThinking} terminalWidth={terminalWidth} />;
				}}
			</Static>

			{displayedBuffer && !isSuppressedByStatic ? renderStreamingTail(displayedBuffer, grouped, theme, terminalWidth) : null}

			{/* Pending tool call indicator — ● 闪烁表示工具正在执行中 */}
			{pendingToolCall ? (
				<BlinkingToolIndicator
					pending={pendingToolCall}
					theme={theme}
					displayedBuffer={displayedBuffer}
					isSuppressedByStatic={isSuppressedByStatic}
				/>
			) : null}
		</>
	);
}

function BlinkingToolIndicator({
	pending,
	theme,
	displayedBuffer,
	isSuppressedByStatic,
}: {
	pending: PendingToolCall;
	theme: ThemeConfig;
	displayedBuffer: string;
	isSuppressedByStatic: boolean;
}): React.JSX.Element {
	const [visible, setVisible] = useState(true);
	const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

	useEffect(() => {
		intervalRef.current = setInterval(() => {
			setVisible((v) => !v);
		}, 500);
		return () => {
			if (intervalRef.current) {
				clearInterval(intervalRef.current);
			}
		};
	}, []);

	const summary = pending.tool_input
		? summarizeInput(pending.tool_name, pending.tool_input, pending.tool_name)
		: null;
	const content = summary ? `${pending.tool_name} (${summary})` : pending.tool_name;

	return (
		<Box marginTop={displayedBuffer || isSuppressedByStatic ? 0 : 1}>
			<Text color={theme.colors.info}>
				{visible ? theme.icons.tool : ' '}
				{' '}
			</Text>
			<Text bold>{content}</Text>
		</Box>
	);
}

function isEmptyItem(item: TranscriptItem): boolean {
	if (item.role === 'assistant' && (!item.text || item.text.trim() === '') && (!item.reasoning || item.reasoning.trim() === '')) {
		return true;
	}
	if (item.role === 'assistant_streaming' && (!item.text || item.text.trim() === '')) {
		return true;
	}
	if (item.role === 'tool' && (!item.text || item.text.trim() === '') && !item.tool_name) {
		return true;
	}
	return false;
}

type GroupEntry =
	| {type: 'single'; item: TranscriptItem; role: string}
	| {type: 'tool_group'; toolItem: TranscriptItem; resultItem: TranscriptItem | null; role: string}
	| {type: 'welcome'; role: string};

type DisplayEntry = {
	key: string;
	entry: GroupEntry;
	prevRole?: string;
};

function groupToolItems(items: TranscriptItem[]): GroupEntry[] {
	const result: GroupEntry[] = [];
	const usedResults = new Set<number>();
	const resultToTool = new Map<number, number>();
	let i = 0;
	while (i < items.length) {
		const item = items[i];
		if (item.role === 'tool') {
			let resultItem: TranscriptItem | null = null;
			for (let j = i + 1; j < items.length; j++) {
				if (items[j].role === 'tool_result' && items[j].tool_name === item.tool_name && !usedResults.has(j)) {
					resultItem = items[j];
					usedResults.add(j);
					resultToTool.set(j, i);
					break;
				}
			}
			result.push({type: 'tool_group', toolItem: item, resultItem, role: 'tool'});
			i += 1;
			continue;
		}
		if (item.role === 'tool_result' && usedResults.has(i)) {
			const toolIdx = resultToTool.get(i)!;
			let hasConcurrentTool = false;
			for (let k = toolIdx + 1; k < i; k++) {
				if (items[k].role === 'tool') {
					hasConcurrentTool = true;
					break;
				}
			}
			if (!hasConcurrentTool) {
				result.push({type: 'single', item, role: 'tool_result'});
			}
			i += 1;
			continue;
		}
		result.push({type: 'single', item, role: item.role});
		i += 1;
	}
	return result;
}

function ToolGroupRow({
	toolItem,
	resultItem,
	theme,
	prevRole,
	terminalWidth,
}: {
	toolItem: TranscriptItem;
	resultItem: TranscriptItem | null;
	theme: ThemeConfig;
	prevRole?: string;
	terminalWidth: number;
}): React.JSX.Element {
	const toolName = toolItem.tool_name ?? 'tool';
	const summary = summarizeInput(toolName, toolItem.tool_input, toolItem.text);
	const needsGap = prevRole !== undefined && prevRole !== 'tool' && prevRole !== 'tool_result';
	const prefix = `${theme.icons.tool} `;
	const continuationPrefix = ' '.repeat(stringWidth(prefix));
	const content = summary ? `${toolName} (${summary})` : toolName;
	const wrapped = wrapForPrefix(content, terminalWidth, prefix);
	const continuationDim = false;

	return (
		<Box flexDirection="column" marginTop={needsGap ? 1 : 0}>
			{wrapped.map((line, i) => (
				<Box key={i}>
					{i === 0 ? (
						<Text>
							<Text color={theme.colors.info}>{prefix}</Text>
							<Text bold>{line}</Text>
						</Text>
					) : (
						<Text dimColor={continuationDim}>{continuationPrefix}{line}</Text>
					)}
				</Box>
			))}
		</Box>
	);
}

function ToolResultBlock({
	item,
	theme,
	terminalWidth,
}: {
	item: TranscriptItem;
	theme: ThemeConfig;
	terminalWidth: number;
}): React.JSX.Element {
	const lines = item.text.split('\n').filter((l) => l.trim() !== '');
	const truncated = lines.length > MAX_RESULT_LINES;
	const display = truncated
		? [...lines.slice(0, MAX_RESULT_LINES), `… +${lines.length - MAX_RESULT_LINES} lines`]
		: lines;

	if (display.length === 0) {
		return (
			<Box>
				<Text dimColor>{`  ${theme.icons.resultPrefix} `}</Text>
				<Text color={theme.colors.success}>{theme.icons.check}</Text>
			</Box>
		);
	}

	const isError = item.is_error;
	const icon = isError ? theme.icons.cross : theme.icons.check;
	const iconColor = isError ? theme.colors.error : theme.colors.success;
	const firstPrefix = `  ${theme.icons.resultPrefix} ${icon} `;
	const firstPrefixText = `  ${theme.icons.resultPrefix} `;
	const continuationPrefix = '      ';
	const firstWidth = Math.max(MIN_WRAP_WIDTH, terminalWidth - stringWidth(firstPrefix) - WIDTH_SAFETY_EXTRA);
	const continuationWidth = Math.max(MIN_WRAP_WIDTH, terminalWidth - stringWidth(continuationPrefix) - WIDTH_SAFETY_EXTRA);

	return (
		<Box flexDirection="column">
			{display.map((line, i) => {
				// 差异行着色：+行绿色，-行红色，@@行青色
				let lineColor: string | undefined = undefined;
				let lineDim = !isError;
				const trimmedLine = line.trimStart();
				if (trimmedLine.startsWith('+') && !trimmedLine.startsWith('+++')) {
					lineColor = theme.colors.success;
					lineDim = false;
				} else if (trimmedLine.startsWith('-') && !trimmedLine.startsWith('---')) {
					lineColor = theme.colors.error;
					lineDim = false;
				} else if (trimmedLine.startsWith('@@')) {
					lineColor = theme.colors.info;
					lineDim = false;
				}
				// 逐行截断到终端宽度加省略号，避免长行换行破坏预览截断效果
					const width = i === 0 ? firstWidth : continuationWidth;
					const displayLine = truncateToDisplayWidth(line, width);
					const showLeadingIcon = i === 0;

					return (
						<Box key={i}>
							<Text dimColor>{showLeadingIcon ? firstPrefixText : continuationPrefix}</Text>
							{showLeadingIcon ? (
								<Text color={iconColor}>{icon} </Text>
							) : null}
							<Text color={isError ? theme.colors.error : lineColor} dimColor={isError ? false : lineDim}>
								{displayLine}
							</Text>
						</Box>
					);
			})}
		</Box>
	);
}

function MessageRow({
	item,
	theme,
	language,
	prevRole,
	showThinking = true,
	terminalWidth,
}: {
	item: TranscriptItem;
	theme: ThemeConfig;
	language: UiLanguage;
	prevRole?: string;
	showThinking?: boolean;
	terminalWidth: number;
}): React.JSX.Element {
	switch (item.role) {
		case 'user': {
			const needsDivider = prevRole !== 'user';
			const prefix = `${theme.icons.pointer} `;
			const continuationPrefix = ' '.repeat(stringWidth(prefix));
			const wrapped = wrapForPrefix(item.text, terminalWidth, prefix);
			return (
				<Box flexDirection="column" marginTop={needsDivider ? 1 : 0}>
					{needsDivider ? (
						<Box marginBottom={0}>
							<Text color={theme.colors.text}>{' '}{'─'.repeat(60)}</Text>
						</Box>
					) : null}
					{wrapped.map((line, i) => (
						<Box key={i}>
							{i === 0 ? (
								<Text>
									<Text color={theme.colors.illusion}>{theme.icons.pointer}</Text>
									<Text bold>{' '}{line}</Text>
								</Text>
							) : (
								<Text bold>{continuationPrefix}{line}</Text>
							)}
						</Box>
					))}
				</Box>
			);
		}

		case 'assistant': {
				const sanitized = stripToolCallArtifacts(item.text);
				const hasTags = hasThinkTags(sanitized);
				let cleanText = sanitized;
				let thinkFromTags = '';
				if (hasTags) {
					thinkFromTags = extractThinkContent(sanitized);
					cleanText = stripThinkTags(sanitized);
				}
				const reasoning = showThinking ? mergeReasoning(item.reasoning, thinkFromTags) : '';
				return (
					<Box flexDirection="column">
						{reasoning ? renderReasoningBlock(reasoning, theme, t(language, 'reasoning'), terminalWidth) : null}
						{renderAssistantBlock(cleanText, theme, terminalWidth, t(language, 'assistantReply'))}
					</Box>
				);
			}

		case 'assistant_streaming': {
				const isFirst = prevRole !== 'assistant_streaming';
				if (isFirst) {
					return (
						<Box marginTop={1}>
							<Text color={theme.colors.illusion}>{theme.icons.assistant}</Text>
							<Box marginLeft={1} flexGrow={1}>
								<Text>{item.text}</Text>
							</Box>
						</Box>
					);
				}
				return (
					<Box marginLeft={2}>
						<Text>{item.text}</Text>
					</Box>
				);
			}

		case 'tool_result': {
			return <ToolResultBlock item={item} theme={theme} terminalWidth={terminalWidth} />;
		}

		case 'system': {
			if (!item.text.trim()) {
				return null;
			}
			const sysLines = item.text.split('\n');
			const firstLine = sysLines[0];
			const restLines = sysLines.slice(1);
			return (
				<Box marginTop={1} flexDirection="column">
					<Text>
						<Text color={theme.colors.warning} italic>{theme.icons.system}</Text>
						<Text color={theme.colors.muted} italic>{' '}{firstLine}</Text>
					</Text>
					{restLines.map((line, idx) => (
						<Box key={idx} marginLeft={2}>
							<Text color={theme.colors.muted} italic>{line}</Text>
						</Box>
					))}
				</Box>
			);
		}

		case 'log':
			return (
				<Box>
					<Text dimColor>{item.text}</Text>
				</Box>
			);

		default:
			return (
				<Box>
					<Text>{item.text}</Text>
				</Box>
			);
	}
}

function renderAssistantBlock(text: string, theme: ThemeConfig, terminalWidth: number, label: string): React.JSX.Element | null {
	if (!text) return null;

	return (
		<Box marginTop={1} flexDirection="column">
			<Box>
				<Text color={theme.colors.illusion}>{theme.icons.assistant}</Text>
				<Box marginLeft={1} flexGrow={1}>
					<Text>{'(' + label + ')'}</Text>
				</Box>
			</Box>
			<Box marginLeft={2} flexDirection="column">
				<MarkdownContent text={text} availableWidth={Math.max(MIN_WRAP_WIDTH, terminalWidth - 2 - WIDTH_SAFETY_EXTRA)} />
			</Box>
		</Box>
	);
}


function renderReasoningBlock(text: string, theme: ThemeConfig, label: string, terminalWidth: number): React.JSX.Element | null {
	if (!text.trim()) return null;

	return (
		<Box marginTop={1} flexDirection="column">
			<Box>
				<Text color={theme.colors.muted}>● ({label})</Text>
			</Box>
			<Box marginLeft={2} flexDirection="column">
				<MarkdownContent
					text={text}
					style={{color: theme.colors.muted}}
					availableWidth={Math.max(MIN_WRAP_WIDTH, terminalWidth - 2 - WIDTH_SAFETY_EXTRA)}
				/>
			</Box>
		</Box>
	);
}

function renderStreamingTail(
	text: string,
	grouped: GroupEntry[],
	theme: ThemeConfig,
	terminalWidth: number,
): React.JSX.Element {
	// Filter empty lines to prevent showing golden ● with no text
	const allLines = text.split('\n');
	const lines = allLines.filter(l => l.trim() !== '');
	if (lines.length === 0) return <Box />;

	const hasOverflow = lines.length > STREAMING_TAIL_LINES;
	const tailCount = hasOverflow ? STREAMING_TAIL_LINES - 1 : STREAMING_TAIL_LINES;
	const tailLines = lines.slice(-tailCount);

	const lastStaticRole = grouped.length > 0 ? grouped[grouped.length - 1].role : undefined;
	const showIcon = lastStaticRole !== 'assistant' && lastStaticRole !== 'assistant_streaming';

	return (
		<Box marginTop={1} flexDirection="column">
			{lines.length > STREAMING_TAIL_LINES ? (
				<Box marginLeft={2}>
					<Text dimColor>… {lines.length - STREAMING_TAIL_LINES} lines above</Text>
				</Box>
			) : null}
			{tailLines.map((line, i) => {
				const isFirst = i === 0 && showIcon;
				const prefixWidth = isFirst ? stringWidth(`${theme.icons.assistant} `) : 2;
				const maxWidth = Math.max(MIN_WRAP_WIDTH, terminalWidth - prefixWidth - WIDTH_SAFETY_EXTRA);
				const truncated = truncateToDisplayWidth(line, maxWidth);
				return (
					<Box key={i} marginLeft={isFirst ? 0 : 2}>
						{isFirst ? (
							<>
								<Text color={theme.colors.illusion}>{theme.icons.assistant}</Text>
								<Box marginLeft={1} flexGrow={1}>
									<Text>{truncated}</Text>
								</Box>
							</>
						) : (
							<Text>{truncated}</Text>
						)}
					</Box>
				);
			})}
		</Box>
	);
}

function wrapForPrefix(text: string, terminalWidth: number, prefix: string): string[] {
	const availableWidth = Math.max(MIN_WRAP_WIDTH, terminalWidth - stringWidth(prefix) - WIDTH_SAFETY_EXTRA);
	const sourceLines = text.split('\n');
	const wrapped: string[] = [];
	for (const source of sourceLines) {
		const segments = wrapText(source, availableWidth, {hard: true});
		if (segments.length === 0) {
			wrapped.push('');
			continue;
		}
		wrapped.push(...segments);
	}
	return wrapped.length > 0 ? wrapped : [''];
}

function truncateToDisplayWidth(text: string, maxWidth: number): string {
	if (stringWidth(text) <= maxWidth) {
		return text;
	}
	let result = '';
	let width = 0;
	for (const ch of text) {
		const charWidth = stringWidth(ch);
		if (width + charWidth > Math.max(1, maxWidth - 1)) {
			break;
		}
		result += ch;
		width += charWidth;
	}
	return result + '…';
}

function normalizeTextForCompare(raw: string): string {
	return raw.replace(/\s+/g, ' ').trim();
}

function isTextSubsetOrEqual(a: string, b: string): boolean {
	const normA = normalizeTextForCompare(a);
	const normB = normalizeTextForCompare(b);
	if (!normA || !normB) return false;
	return normA === normB || normA.includes(normB) || normB.includes(normA);
}

function summarizeInput(toolName: string, toolInput?: Record<string, unknown>, fallback?: string): string {
	if (!toolInput) {
		return truncateCommand(fallback ?? '');
	}

	const lower = toolName.toLowerCase();

	if ((lower === 'bash' || lower === 'powershell') && toolInput.command) {
		return truncateCommand(String(toolInput.command));
	}
	if ((lower === 'read' || lower === 'fileread' || lower === 'read_file') && (toolInput.path || toolInput.file_path)) {
		return String(toolInput.path ?? toolInput.file_path);
	}
	if ((lower === 'write' || lower === 'filewrite' || lower === 'write_file') && (toolInput.path || toolInput.file_path)) {
		return String(toolInput.path ?? toolInput.file_path);
	}
	if ((lower === 'edit' || lower === 'fileedit' || lower === 'edit_file') && (toolInput.path || toolInput.file_path)) {
		return String(toolInput.path ?? toolInput.file_path);
	}
	if (lower === 'grep' && toolInput.pattern) {
		return `/${String(toolInput.pattern)}/`;
	}
	if (lower === 'glob' && toolInput.pattern) {
		return String(toolInput.pattern);
	}
	if (lower === 'agent' && toolInput.description) {
		return truncateCommand(String(toolInput.description));
	}
	if (lower === 'todowrite' || lower === 'todo_write') {
		const todos = toolInput.todos;
		if (Array.isArray(todos)) {
			const total = todos.length;
			const completed = todos.filter((t: {status: string}) => t.status === 'completed').length;
			return `${completed}/${total} tasks`;
		}
	}
	if (lower === 'ask_user_question') {
		const questions = toolInput.questions;
		if (Array.isArray(questions) && questions.length > 0) {
			const q = questions[0] as Record<string, unknown>;
			return truncateCommand(String(q.question ?? ''));
		}
	}

	const entries = Object.entries(toolInput);
	if (entries.length > 0) {
		const [key, val] = entries[0];
		return truncateCommand(`${key}=${String(val)}`);
	}

	return truncateCommand(fallback ?? '');
}

// 参考 claude-code 的截断策略：先按行截断，再按字符截断
function truncateCommand(str: string): string {
	// 1. 按行分割
	const lines = str.split('\n');

	// 2. 移除每行首尾空格，过滤空行
	const cleanedLines = lines.map(l => l.trim()).filter(l => l.length > 0);

	// 3. 按行截断（最多 MAX_COMMAND_LINES 行）
	const truncatedLines = cleanedLines.length > MAX_COMMAND_LINES
		? [...cleanedLines.slice(0, MAX_COMMAND_LINES)]
		: cleanedLines;

	// 4. 合并为单行
	let result = truncatedLines.join(' ');

	// 5. 按字符截断
	const needsCharTruncation = result.length > MAX_COMMAND_CHARS || cleanedLines.length > MAX_COMMAND_LINES;
	if (needsCharTruncation && result.length > MAX_COMMAND_CHARS) {
		result = result.slice(0, MAX_COMMAND_CHARS);
		// 优先在分号处截断（命令分隔符）
		const lastSemicolon = result.lastIndexOf(';');
		if (lastSemicolon > MAX_COMMAND_CHARS * 0.3) {
			result = result.slice(0, lastSemicolon + 1);
		} else {
			// 其次在空格处截断
			const lastSpace = result.lastIndexOf(' ');
			if (lastSpace > MAX_COMMAND_CHARS * 0.5) {
				result = result.slice(0, lastSpace);
			}
		}
	}

	// 6. 添加省略号
	if (needsCharTruncation) {
		result += '…';
	}

	return result;
}
