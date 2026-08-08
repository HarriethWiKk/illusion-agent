/**
 * @fileoverview 搜索工具渲染实现（grep + glob）
 *
 * grep 显示匹配行和统计，glob 显示文件列表。
 *
 * @module tools/implementations/SearchTool
 */

import type {Tool} from '../ToolInterface.js';

export const grepTool: Tool = {
	name: 'grep',

	displayName(): string {
		return 'Grep';
	},

	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		const parts: string[] = [];
		if (input.pattern) {
			parts.push(`pattern: "${input.pattern}"`);
		}
		if (input.path) {
			parts.push(`path: "${input.path}"`);
		}
		return parts.join(', ');
	},

	renderToolResultMessage(
		result: string,
		_input?: Record<string, unknown>,
		_isBrief?: boolean,
		structuredOutput?: Record<string, unknown>,
	): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;

		if (metadata?.mode === 'count') {
			return `Found ${metadata.match_count} matches across ${metadata.file_count} file(s)`;
		}

		if (metadata?.mode === 'files_with_matches') {
			const files = (metadata.matches as Array<{file: string}>) ?? [];
			return `Found ${files.length} file(s)`;
		}

		const lines = result.split('\n').filter((l) => l.trim() !== '');
		return `Found ${lines.length} line(s)`;
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.pattern) return 'Searching';
		return `Searching for ${input.pattern}`;
	},
};

export const globTool: Tool = {
	name: 'glob',

	displayName(): string {
		return 'Glob';
	},

	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		const parts: string[] = [];
		if (input.pattern) {
			parts.push(`pattern: "${input.pattern}"`);
		}
		if (input.path) {
			parts.push(`path: "${input.path}"`);
		}
		return parts.join(', ');
	},

	renderToolResultMessage(
		result: string,
		_input?: Record<string, unknown>,
		_isBrief?: boolean,
		structuredOutput?: Record<string, unknown>,
	): string {
		const metadata = structuredOutput as Record<string, unknown> | undefined;

		if (metadata?.files && Array.isArray(metadata.files)) {
			const files = metadata.files as string[];
			return `Found ${files.length} file(s)`;
		}

		const lines = result.split('\n').filter((l) => l.trim() !== '');
		return `Found ${lines.length} file(s)`;
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.pattern) return 'Finding files';
		return `Finding ${input.pattern}`;
	},
};
