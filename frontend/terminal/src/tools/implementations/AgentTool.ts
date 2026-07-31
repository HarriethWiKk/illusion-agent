/**
 * @fileoverview Agent 工具渲染实现
 *
 * 子代理渲染，支持进度追踪、紧凑模式、后台代理等。
 *
 * @module tools/implementations/AgentTool
 */

import type {Tool} from '../ToolInterface.js';

const MAX_RESULT_LINES = 10;

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
		result: string,
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

		// 显示 agent 最终回复，截断到 MAX_RESULT_LINES（与 bash 工具一致）
		if (!result || result.trim() === '') {
			return 'Done';
		}
		const lines = result.split('\n').filter(l => l.length > 0);
		if (lines.length > MAX_RESULT_LINES) {
			return [...lines.slice(0, MAX_RESULT_LINES), `… +${lines.length - MAX_RESULT_LINES} lines`].join('\n');
		}
		return lines.join('\n');
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.description) return 'Running task';
		return String(input.description);
	},
};
