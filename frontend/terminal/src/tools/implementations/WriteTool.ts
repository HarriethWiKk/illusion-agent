/**
 * @fileoverview 文件写入工具渲染实现
 *
 * 新建时显示行数和代码预览，更新时显示 diff。
 *
 * @module tools/implementations/WriteTool
 */

import type {Tool} from '../ToolInterface.js';

export const writeTool: Tool = {
	name: 'write_file',

	displayName(): string {
		return 'Write';
	},

	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		return String(input.path ?? input.file_path ?? '');
	},

	renderToolResultMessage(
		result: string,
		_input?: Record<string, unknown>,
		_isBrief?: boolean,
		structuredOutput?: Record<string, unknown>,
	): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const isCreate = metadata?.is_create !== false;
		const lineCount = metadata?.line_count ?? result.split('\n').length;
		const filePath = metadata?.file_path ?? '';

		if (isCreate) {
			return `Wrote ${lineCount} lines to ${filePath}`;
		}

		// 更新：显示 diff 行
		const lines = result.split('\n').filter((l) => l.trim() !== '');
		if (lines.length === 0) {
			return '(No diff)';
		}
		return lines.slice(0, 15).join('\n');
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input) return 'Writing file';
		const path = String(input.path ?? input.file_path ?? '');
		return path ? `Writing ${path}` : 'Writing file';
	},
};
