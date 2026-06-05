/**
 * @fileoverview Web 工具渲染实现（web_search + web_fetch）
 */
import type {Tool} from '../ToolInterface.js';

export const webSearchTool: Tool = {
	name: 'web_search',
	displayName: () => 'Web Search',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.query) return '';
		return `"${String(input.query)}"`;
	},
	renderToolResultMessage(_result: string, _input?: Record<string, unknown>, _isBrief?: boolean, structuredOutput?: Record<string, unknown>): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const searchCount = metadata?.search_count ?? 1;
		const durationMs = metadata?.duration_ms;
		const timeStr = durationMs ? ` in ${Number(durationMs) >= 1000 ? `${(Number(durationMs) / 1000).toFixed(1)}s` : `${durationMs}ms`}` : '';
		return `Did ${searchCount} search(es)${timeStr}`;
	},
	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.query) return 'Searching the web';
		return `Searching for ${input.query}`;
	},
};

export const webFetchTool: Tool = {
	name: 'web_fetch',
	displayName: () => 'Fetch',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.url) return '';
		return String(input.url);
	},
	renderToolResultMessage(_result: string, _input?: Record<string, unknown>, _isBrief?: boolean, structuredOutput?: Record<string, unknown>): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const statusCode = metadata?.status_code;
		const contentSize = metadata?.content_size;
		const parts: string[] = ['Received'];
		if (contentSize) {
			const size = Number(contentSize);
			parts.push(size < 1024 ? `${size}B` : size < 1048576 ? `${(size / 1024).toFixed(1)}KB` : `${(size / 1048576).toFixed(1)}MB`);
		}
		if (statusCode) {
			parts.push(`(${statusCode} ${Number(statusCode) === 200 ? 'OK' : ''})`.trim());
		}
		return parts.join(' ');
	},
	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.url) return 'Fetching web page';
		return `Fetching ${String(input.url).slice(0, 60)}`;
	},
};
