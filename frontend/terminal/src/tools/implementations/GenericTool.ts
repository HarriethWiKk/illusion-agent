/**
 * @fileoverview 通用回退工具渲染
 */
import type {Tool} from '../ToolInterface.js';

function safeStringify(val: unknown): string {
	if (val === null || val === undefined) return '';
	if (typeof val === 'string') return val;
	if (typeof val === 'number' || typeof val === 'boolean') return String(val);
	if (Array.isArray(val)) {
		if (val.length === 0) return '[]';
		return `[${val.length} items]`;
	}
	if (typeof val === 'object') {
		const obj = val as Record<string, unknown>;
		const keys = Object.keys(obj);
		if (keys.length === 0) return '{}';
		const firstKey = keys[0];
		const firstVal = safeStringify(obj[firstKey]);
		if (keys.length === 1) return `{${firstKey}: ${firstVal}}`;
		return `{${firstKey}: ${firstVal}, ...}`;
	}
	return String(val);
}

export const genericTool: Tool = {
	name: '*',
	displayName(): string { return ''; },
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		const entries = Object.entries(input);
		if (entries.length === 0) return '';
		const [key, val] = entries[0];
		const valStr = safeStringify(val);
		if (valStr.length > 80) return `${key}=${valStr.slice(0, 80)}…`;
		return `${key}=${valStr}`;
	},
	renderToolResultMessage(result: string): string {
		if (!result || result.trim() === '') return '(No output)';
		const lines = result.split('\n').filter((l) => l.trim() !== '');
		if (lines.length <= 5) return lines.join('\n');
		return [...lines.slice(0, 5), `… +${lines.length - 5} lines`].join('\n');
	},
	getActivityDescription(): string | null { return null; },
};

export function createGenericTool(name: string, displayName: string, getActivity?: (input?: Record<string, unknown>) => string | null): Tool {
	return { ...genericTool, name, displayName: () => displayName, getActivityDescription: getActivity ?? (() => null) };
}
