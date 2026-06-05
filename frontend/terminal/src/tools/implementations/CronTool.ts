/**
 * @fileoverview Cron 工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const cronTool: Tool = {
	name: 'cron',
	displayName: () => 'Cron',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		if (input.action === 'create' && input.cron) {
			const prompt = String(input.prompt ?? '').slice(0, 60);
			return `"${input.cron}": ${prompt}`;
		}
		if (input.action === 'delete' && input.id) {
			return String(input.id);
		}
		return String(input.action ?? '');
	},
	renderToolResultMessage(result: string): string {
		return result.split('\n').find((l) => l.trim()) ?? '(Done)';
	},
};
