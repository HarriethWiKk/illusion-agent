/**
 * @fileoverview MCP 动态工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const mcpTool: Tool = {
	name: 'mcp',
	displayName: () => 'mcp',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		return Object.entries(input).slice(0, 3).map(([k, v]) => {
			const val = String(v);
			return `${k}: ${val.length > 80 ? val.slice(0, 80) + '…' : val}`;
		}).join(', ');
	},
	renderToolResultMessage(result: string): string {
		if (!result || result.trim() === '') return '(No content)';
		const lines = result.split('\n').filter((l) => l.trim() !== '');
		if (lines.length <= 5) return lines.join('\n');
		return [...lines.slice(0, 5), `… +${lines.length - 5} lines`].join('\n');
	},
};

export const listMcpResourcesTool: Tool = { ...mcpTool, name: 'list_mcp_resources', displayName: () => 'listMcpResources' };
export const readMcpResourceTool: Tool = { ...mcpTool, name: 'read_mcp_resource', displayName: () => 'readMcpResource' };
