import React, {useState, useEffect, useCallback} from 'react';
import {Text, useInput} from 'ink';
import chalk from 'chalk';

interface TextPosition {
	line: number;
	column: number;
}

interface CursorState {
	cursorOffset: number;
	desiredColumn: number | null;
}

/**
 * 将字符偏移量转换为行列位置
 */
function offsetToPosition(text: string, offset: number): TextPosition {
	let line = 0;
	let column = 0;
	for (let i = 0; i < offset && i < text.length; i++) {
		if (text[i] === '\n') {
			line++;
			column = 0;
		} else {
			column++;
		}
	}
	return {line, column};
}

/**
 * 获取指定行的起始偏移量和行内容
 */
function getLineInfo(text: string, lineNumber: number): {startOffset: number; content: string} {
	const lines = text.split('\n');
	let offset = 0;
	for (let i = 0; i < lineNumber && i < lines.length; i++) {
		offset += lines[i].length + 1; // +1 for \n
	}
	return {
		startOffset: offset,
		content: lines[lineNumber] ?? '',
	};
}

/**
 * 获取文本总行数
 */
function getLineCount(text: string): number {
	if (text.length === 0) return 1;
	return text.split('\n').length;
}

export default function MultilineTextInput({
	value: originalValue,
	placeholder = '',
	focus = true,
	showCursor = true,
	onChange,
	onSubmit,
}: {
	value: string;
	placeholder?: string;
	focus?: boolean;
	showCursor?: boolean;
	onChange: (value: string) => void;
	onSubmit?: (value: string) => void;
}): React.JSX.Element {
	const [state, setState] = useState<CursorState>({
		cursorOffset: (originalValue || '').length,
		desiredColumn: null,
	});

	// 外部 value 变化时，钳位光标位置
	useEffect(() => {
		setState(prev => {
			if (!focus || !showCursor) return prev;
			const maxOffset = (originalValue || '').length;
			if (prev.cursorOffset > maxOffset) {
				return {cursorOffset: maxOffset, desiredColumn: null};
			}
			return prev;
		});
	}, [originalValue, focus, showCursor]);

	const {cursorOffset, desiredColumn} = state;

	const handleKeyDown = useCallback((input: string, key: {
		upArrow?: boolean;
		downArrow?: boolean;
		leftArrow?: boolean;
		rightArrow?: boolean;
		return?: boolean;
		backspace?: boolean;
		delete?: boolean;
		ctrl?: boolean;
		shift?: boolean;
		tab?: boolean;
	}) => {
		// Ctrl 组合键：不插入字符
		if (key.ctrl) {
			if (input === 'u') {
				onChange('');
				setState({cursorOffset: 0, desiredColumn: null});
				return;
			}
			// 其他 Ctrl 组合键（c/o/x 等）不插入，让 App 层处理
			return;
		}

		// Tab 不处理（留给命令选择器）
		if (key.tab) return;

		// \n (Ctrl+J) 插入换行（终端中 \n 与 \r 是不同字节，可靠区分）
		if (input === '\n') {
			const nextValue = originalValue.slice(0, cursorOffset) + '\n' + originalValue.slice(cursorOffset);
			onChange(nextValue);
			setState({cursorOffset: cursorOffset + 1, desiredColumn: null});
			return;
		}

		// Enter (\r) 提交（Shift+Enter 在大多数终端中与 Enter 发送相同的 \r，
		// 无法区分，因此仅支持 Ctrl+J 换行）
		if (key.return) {
			onSubmit?.(originalValue);
			return;
		}

		// 上箭头：移动到上一行的同列位置
		if (key.upArrow) {
			if (!showCursor) return;
			const pos = offsetToPosition(originalValue, cursorOffset);
			if (pos.line === 0) {
				// 已经在第一行，移到行首
				if (pos.column > 0) {
					setState({cursorOffset: cursorOffset - pos.column, desiredColumn: null});
				}
				return;
			}
			const targetColumn = desiredColumn ?? pos.column;
			const prevLine = getLineInfo(originalValue, pos.line - 1);
			const newColumn = Math.min(targetColumn, prevLine.content.length);
			setState({
				cursorOffset: prevLine.startOffset + newColumn,
				desiredColumn: targetColumn,
			});
			return;
		}

		// 下箭头：移动到下一行的同列位置
		if (key.downArrow) {
			if (!showCursor) return;
			const totalLines = getLineCount(originalValue);
			const pos = offsetToPosition(originalValue, cursorOffset);
			if (pos.line >= totalLines - 1) {
				// 已经在最后一行，移到行尾
				if (cursorOffset < originalValue.length) {
					setState({cursorOffset: originalValue.length, desiredColumn: null});
				}
				return;
			}
			const targetColumn = desiredColumn ?? pos.column;
			const nextLine = getLineInfo(originalValue, pos.line + 1);
			const newColumn = Math.min(targetColumn, nextLine.content.length);
			setState({
				cursorOffset: nextLine.startOffset + newColumn,
				desiredColumn: targetColumn,
			});
			return;
		}

		// 左右箭头时清除 desiredColumn
		if (key.leftArrow) {
			if (showCursor && cursorOffset > 0) {
				setState({cursorOffset: cursorOffset - 1, desiredColumn: null});
			}
			return;
		}
		if (key.rightArrow) {
			if (showCursor && cursorOffset < originalValue.length) {
				setState({cursorOffset: cursorOffset + 1, desiredColumn: null});
			}
			return;
		}

		// 退格/删除（统一处理：Windows Terminal 的 Backspace 发送 \x7f 被解析为 key.delete，
		// 与 ink-text-input 保持一致，都删除光标前一个字符）
		if (key.backspace || key.delete) {
			if (cursorOffset > 0) {
				const nextValue = originalValue.slice(0, cursorOffset - 1) + originalValue.slice(cursorOffset);
				onChange(nextValue);
				setState({cursorOffset: cursorOffset - 1, desiredColumn: null});
			}
			return;
		}

		// 普通字符输入
		if (input.length > 0) {
			const nextValue = originalValue.slice(0, cursorOffset) + input + originalValue.slice(cursorOffset);
			onChange(nextValue);
			setState({cursorOffset: cursorOffset + input.length, desiredColumn: null});
		}
	}, [originalValue, cursorOffset, showCursor, onChange, onSubmit]);

	useInput(handleKeyDown, {isActive: focus});

	// --- 渲染 ---
	const lines = originalValue.split('\n');

	if (originalValue.length === 0 && placeholder) {
		const renderedPlaceholder = showCursor && focus
			? chalk.inverse(placeholder[0] ?? ' ') + chalk.grey(placeholder.slice(1))
			: chalk.grey(placeholder);
		return <Text>{renderedPlaceholder}</Text>;
	}

	const renderedLines: string[] = [];
	let runningOffset = 0;

	for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
		const line = lines[lineIdx];
		const lineStart = runningOffset;
		const lineEnd = lineStart + line.length;

		if (showCursor && focus && cursorOffset >= lineStart && cursorOffset <= lineEnd) {
			// 光标在这一行
			const cursorCol = cursorOffset - lineStart;
			let rendered = '';
			for (let i = 0; i < line.length; i++) {
				rendered += i === cursorCol ? chalk.inverse(line[i]) : line[i];
			}
			if (cursorCol === line.length) {
				rendered += chalk.inverse(' ');
			}
			renderedLines.push(rendered);
		} else {
			renderedLines.push(line || ' ');
		}

		runningOffset = lineEnd + 1; // +1 for \n
	}

	// 空文本且无 placeholder
	if (renderedLines.length === 0) {
		renderedLines.push(showCursor && focus ? chalk.inverse(' ') : ' ');
	}

	return <Text>{renderedLines.join('\n')}</Text>;
}
