/**
 * @fileoverview 文件编辑工具渲染实现
 *
 * 显示结构化统一 diff，带框线和着色。
 *
 * @module tools/implementations/EditTool
 */

import type {Tool} from '../ToolInterface.js';

interface DiffHunk {
	old_start: number;
	old_lines: number;
	new_start: number;
	new_lines: number;
	lines: string[];
}

export const editTool: Tool = {
	name: 'edit_file',

	displayName(input?: Record<string, unknown>): string {
		if (!input?.old_string || String(input.old_string).trim() === '') {
			return 'Create';
		}
		return 'Update';
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
		if (structuredOutput?.hunks && Array.isArray(structuredOutput.hunks)) {
			// 从结构化 diff 提取文本行
			const lines: string[] = [];
			for (const hunk of (structuredOutput.hunks as DiffHunk[]).slice(0, 3)) {
				lines.push(`@@ -${hunk.old_start},${hunk.old_lines} +${hunk.new_start},${hunk.new_lines} @@`);
				for (const line of hunk.lines.slice(0, 10)) {
					lines.push(line);
				}
			}
			return lines.join('\n');
		}

		const lines = result.split('\n').filter((l) => l.trim() !== '');
		if (lines.length === 0) {
			return '(No diff)';
		}
		return lines.slice(0, 15).join('\n');
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input) return 'Editing file';
		const path = String(input.path ?? input.file_path ?? '');
		return path ? `Editing ${path}` : 'Editing file';
	},
};
