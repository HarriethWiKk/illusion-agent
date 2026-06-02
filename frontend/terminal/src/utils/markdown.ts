/**
 * @fileoverview Markdown 工具模块
 *
 * 提供文本处理相关的工具函数，包括：
 * - ANSI 转义序列处理
 * - 字符串宽度计算
 * - 文本换行
 * - 文本对齐
 *
 * @module markdown
 */

import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';
import wrapAnsi from 'wrap-ansi';

/** 重新导出常用的文本处理工具 */
export {stripAnsi, stringWidth, wrapAnsi};

/**
 * 文本对齐填充
 *
 * 根据指定的对齐方式，在内容周围添加空格以达到目标宽度。
 *
 * @param content - 原始内容
 * @param displayWidth - 内容的显示宽度（考虑多字节字符）
 * @param targetWidth - 目标宽度
 * @param align - 对齐方式：'left'（左对齐）、'center'（居中）、'right'（右对齐）
 * @returns 填充后的字符串
 */
export function padAligned(
	content: string,
	displayWidth: number,
	targetWidth: number,
	align: 'left' | 'center' | 'right' | null | undefined,
): string {
	const padding = Math.max(0, targetWidth - displayWidth);
	if (align === 'center') {
		const leftPad = Math.floor(padding / 2);
		return ' '.repeat(leftPad) + content + ' '.repeat(padding - leftPad);
	}
	if (align === 'right') {
		return ' '.repeat(padding) + content;
	}
	return content + ' '.repeat(padding);
}

/**
 * 文本换行
 *
 * 将文本按指定宽度换行，支持硬换行（在单词内断开）和软换行（在空格处断开）。
 *
 * @param text - 要换行的文本
 * @param width - 每行的最大宽度
 * @param options - 换行选项
 * @param options.hard - 是否启用硬换行（在单词内断开），默认为 false
 * @returns 换行后的字符串数组
 */
export function wrapText(text: string, width: number, options?: {hard?: boolean}): string[] {
	if (width <= 0) return [text];
	const trimmedText = text.trimEnd();
	const wrapped = wrapAnsi(trimmedText, width, {
		hard: options?.hard ?? false,
		trim: false,
	});
	const lines = wrapped.split('\n').filter((line) => line.length > 0);
	return lines.length > 0 ? lines : [''];
}
