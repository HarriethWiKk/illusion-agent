/**
 * @fileoverview Agent 工具渲染实现
 *
 * 子代理渲染，支持进度追踪、紧凑模式、后台代理等。
 *
 * @module tools/implementations/AgentTool
 */

import type {Tool} from '../ToolInterface.js';

function formatTokens(tokens: number): string {
	if (tokens < 1000) return String(tokens);
	return `${(tokens / 1000).toFixed(1)}K`;
}

function formatDuration(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

export const agentTool: Tool = {
	name: 'agent',

	displayName(input?: Record<string, unknown>): string {
		if (!input) return 'Agent';
		const agentType = String(input.subagent_type ?? '');
		if (agentType && agentType !== 'worker') {
			return agentType.charAt(0).toUpperCase() + agentType.slice(1);
		}
		return 'Agent';
	},

	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.description) return '';
		return String(input.description);
	},

	renderToolResultMessage(
		_result: string,
		_input?: Record<string, unknown>,
		_isBrief?: boolean,
		structuredOutput?: Record<string, unknown>,
	): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const status = metadata?.status ?? 'completed';

		if (status === 'backgrounded') {
			return 'Backgrounded agent';
		}

		if (status === 'remote_launched') {
			return 'Remote agent launched';
		}

		return 'Done';
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.description) return 'Running task';
		return String(input.description);
	},
};
