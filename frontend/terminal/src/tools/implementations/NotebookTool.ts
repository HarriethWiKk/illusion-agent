/**
 * @fileoverview Notebook 编辑工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const notebookTool: Tool = {
	name: 'notebook_edit',
	displayName: () => 'Edit Notebook',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		const path = String(input.path ?? input.notebook_path ?? '');
		const cellId = input.cell_id ? ` @${input.cell_id}` : '';
		return `${path}${cellId}`;
	},
	renderToolResultMessage(result: string): string {
		const lines = result.split('\n').filter((l) => l.trim() !== '');
		if (lines.length === 0) return 'Updated cell';
		return `Updated cell:\n${lines.slice(0, 5).join('\n')}`;
	},
	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input) return 'Editing notebook';
		const path = String(input.path ?? input.notebook_path ?? '');
		return path ? `Editing notebook ${path}` : 'Editing notebook';
	},
};
