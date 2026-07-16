/**
 * @fileoverview 文本测量核心
 *
 * 将文本按显示宽度换行为 display lines，维护 offset ↔ (line, column) 映射。
 * 使用 string-width 处理 CJK/全角字符的显示宽度。
 *
 * @module MeasuredText
 */

import stringWidth from 'string-width';
import wrapAnsi from 'wrap-ansi';

/**
 * 换行后的显示行
 */
export interface WrappedLine {
	/** 该 display line 的文本内容 */
	text: string;
	/** 在原文中的起始字符偏移量 */
	startOffset: number;
	/** 是否由 \n 分隔（true=逻辑行首，false=wrap续行） */
	precededByNewline: boolean;
	/** 原文中该行后是否紧跟 \n */
	endsWithNewline: boolean;
}

/**
 * 文本测量核心类
 *
 * 将文本按显示宽度换行为 display lines，维护 offset ↔ (line, column) 映射。
 * 使用 string-width 处理 CJK/全角字符的显示宽度。
 */
export class MeasuredText {
	readonly text: string;
	readonly columns: number;
	private _wrappedLines: WrappedLine[] | undefined;

	constructor(text: string, columns: number) {
		this.text = text.normalize('NFC');
		this.columns = columns;
	}

	/**
	 * 惰性计算并缓存换行结果
	 */
	private get wrappedLines(): WrappedLine[] {
		if (!this._wrappedLines) {
			this._wrappedLines = this.measureWrappedText();
		}
		return this._wrappedLines;
	}

	/**
	 * 获取换行后的显示行数组（仅文本）
	 *
	 * wrap 续行会 trimStart 去掉前导空白（这些空白属于原文中的续接）。
	 */
	getWrappedText(): string[] {
		return this.wrappedLines.map(line =>
			line.precededByNewline ? line.text : line.text.trimStart()
		);
	}

	/**
	 * 获取带元数据的换行行数组
	 */
	getWrappedLines(): WrappedLine[] {
		return this.wrappedLines;
	}

	get lineCount(): number {
		return this.wrappedLines.length;
	}

	getLineLength(line: number): number {
		const lines = this.wrappedLines;
		const wrapped = lines[Math.max(0, Math.min(line, lines.length - 1))];
		if (!wrapped) return 0;
		return stringWidth(wrapped.text);
	}

	/**
	 * 测量并生成换行后的显示行数组
	 *
	 * 算法：
	 * 1. 用 wrap-ansi 按列宽 wrap（hard=true, trim=false）
	 * 2. 将 wrap 后的每行映射回原文中的 startOffset
	 * 3. 标记 precededByNewline 和 endsWithNewline
	 */
	private measureWrappedText(): WrappedLine[] {
		const wrappedText = wrapAnsi(this.text, this.columns, {
			hard: true,
			trim: false,
		});

		const result: WrappedLine[] = [];
		let searchOffset = 0;
		let lastNewLinePos = -1;

		const lines = wrappedText.split('\n');
		for (let i = 0; i < lines.length; i++) {
			const lineText = lines[i]!;
			const isPrecededByNewline = (startOffset: number): boolean =>
				i === 0 || (startOffset > 0 && this.text[startOffset - 1] === '\n');

			if (lineText.length === 0) {
				// 空行：找下一个 \n
				lastNewLinePos = this.text.indexOf('\n', lastNewLinePos + 1);
				if (lastNewLinePos !== -1) {
					const startOffset = lastNewLinePos;
					result.push({
						text: lineText,
						startOffset,
						precededByNewline: isPrecededByNewline(startOffset),
						endsWithNewline: true,
					});
				} else {
					// 文本末尾的空行
					const startOffset = this.text.length;
					result.push({
						text: lineText,
						startOffset,
						precededByNewline: isPrecededByNewline(startOffset),
						endsWithNewline: false,
					});
				}
			} else {
				// 非空行：在原文中查找匹配位置
				const startOffset = this.text.indexOf(lineText, searchOffset);
				if (startOffset === -1) {
					throw new Error('Failed to find wrapped line in text');
				}
				searchOffset = startOffset + lineText.length;

				const potentialNewlinePos = startOffset + lineText.length;
				const endsWithNewline =
					potentialNewlinePos < this.text.length &&
					this.text[potentialNewlinePos] === '\n';

				if (endsWithNewline) {
					lastNewLinePos = potentialNewlinePos;
				}

				result.push({
					text: lineText,
					startOffset,
					precededByNewline: isPrecededByNewline(startOffset),
					endsWithNewline,
				});
			}
		}

		return result;
	}

	/**
	 * 根据字符偏移量获取显示坐标 {line, column}
	 *
	 * @param offset - 字符偏移量
	 * @returns {line: display line 索引, column: 显示宽度列号}
	 */
	getPositionFromOffset(offset: number): {line: number; column: number} {
		const lines = this.wrappedLines;
		for (let line = 0; line < lines.length; line++) {
			const current = lines[line]!;
			const next = lines[line + 1];
			if (offset >= current.startOffset && (!next || offset < next.startOffset)) {
				const stringPosInLine = offset - current.startOffset;

				let displayColumn: number;
				if (current.precededByNewline) {
					// 逻辑行首：直接计算显示宽度
					displayColumn = this.stringIndexToDisplayWidth(current.text, stringPosInLine);
				} else {
					// wrap 续行：需要考虑 trim 掉的前导空白
					const trimmed = current.text.trimStart();
					const leadingWs = current.text.length - trimmed.length;
					if (stringPosInLine < leadingWs) {
						displayColumn = 0;
					} else {
						displayColumn = this.stringIndexToDisplayWidth(trimmed, stringPosInLine - leadingWs);
					}
				}

				return {line, column: Math.max(0, displayColumn)};
			}
		}

		// 超出末尾：返回最后一行末尾
		const lastLine = lines[lines.length - 1]!;
		return {line: lines.length - 1, column: stringWidth(lastLine.text)};
	}

	/**
	 * 根据显示坐标 {line, column} 获取字符偏移量
	 *
	 * @param pos - {line: display line 索引, column: 显示宽度列号}
	 * @returns 字符偏移量
	 */
	getOffsetFromPosition(pos: {line: number; column: number}): number {
		const lines = this.wrappedLines;
		const wrapped = lines[Math.max(0, Math.min(pos.line, lines.length - 1))]!;

		// 空行特殊处理
		if (wrapped.text.length === 0 && wrapped.endsWithNewline) {
			return wrapped.startOffset;
		}

		// 处理 wrap 续行的前导空白
		const leadingWs = wrapped.precededByNewline
			? 0
			: wrapped.text.length - wrapped.text.trimStart().length;

		// 将显示列宽转换为字符串索引
		const displayColWithLeading = pos.column + leadingWs;
		const stringIndex = this.displayWidthToStringIndex(wrapped.text, displayColWithLeading);
		const offset = wrapped.startOffset + stringIndex;

		// 不允许超过行尾（除非是该行末尾的 \n）
		const lineEnd = wrapped.startOffset + wrapped.text.length;
		let maxOffset = lineEnd;
		const lineDisplayWidth = stringWidth(wrapped.text);
		if (wrapped.endsWithNewline && pos.column > lineDisplayWidth) {
			maxOffset = lineEnd + 1;
		}

		return Math.min(offset, maxOffset);
	}

	/**
	 * 将字符串索引转换为显示宽度
	 */
	private stringIndexToDisplayWidth(text: string, index: number): number {
		if (index <= 0) return 0;
		if (index >= text.length) return stringWidth(text);
		return stringWidth(text.substring(0, index));
	}

	/**
	 * 将显示宽度转换为字符串索引
	 */
	private displayWidthToStringIndex(text: string, targetWidth: number): number {
		if (targetWidth <= 0) return 0;
		if (!text) return 0;

		let currentWidth = 0;
		// 逐字符遍历，累加显示宽度
		for (let i = 0; i < text.length; i++) {
			const char = text[i]!;
			const charWidth = stringWidth(char);
			if (currentWidth + charWidth > targetWidth) {
				return i;
			}
			currentWidth += charWidth;
		}
		return text.length;
	}
}
