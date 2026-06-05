/**
 * @fileoverview Skill 工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const skillTool: Tool = {
	name: 'skill',
	displayName(): string {
		return 'Skill';
	},
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.name) return '';
		return String(input.name);
	},
	renderToolResultMessage(): string {
		return 'Successfully loaded skill';
	},
	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.name) return 'Loading skill';
		return `Loading skill ${input.name}`;
	},
};
