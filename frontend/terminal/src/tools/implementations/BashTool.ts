/**
 * @fileoverview Bash/PowerShell 工具渲染实现
 *
 * 显示命令文本，结果支持 stdout/stderr、图片检测、后台任务、超时等。
 *
 * @module tools/implementations/BashTool
 */

import type {Tool} from '../ToolInterface.js';

const MAX_COMMAND_LINES = 2;
const MAX_COMMAND_CHARS = 160;
const MAX_RESULT_LINES = 10;

function truncateCommand(str: string): string {
	const lines = str.split('\n');
	const cleaned = lines.map((l) => l.trim()).filter((l) => l.length > 0);
	const truncated = cleaned.length > MAX_COMMAND_LINES
		? cleaned.slice(0, MAX_COMMAND_LINES)
		: cleaned;
	let result = truncated.join(' ');
	if (result.length > MAX_COMMAND_CHARS) {
		result = result.slice(0, MAX_COMMAND_CHARS);
		const lastSpace = result.lastIndexOf(' ');
		if (lastSpace > MAX_COMMAND_CHARS * 0.5) {
			result = result.slice(0, lastSpace);
		}
		result += '…';
	}
	return result;
}

export const bashTool: Tool = {
	name: 'bash',

	displayName(): string {
		return 'Bash';
	},

	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.command) return '';
		return truncateCommand(String(input.command));
	},

	renderToolResultMessage(
		result: string,
		_input?: Record<string, unknown>,
		_isBrief?: boolean,
		structuredOutput?: Record<string, unknown>,
	): string {
		if (!result || result.trim() === '') {
			return '(No output)';
		}

		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const isBackground = metadata?.is_background === true;

		if (isBackground) {
			return 'Running in the background';
		}

		// 截断到 MAX_RESULT_LINES，超出显示 ...N lines
		const maxLines = _isBrief ? 5 : MAX_RESULT_LINES;
		const lines = result.split('\n').filter((l) => l.length > 0);
		if (lines.length > maxLines) {
			return [...lines.slice(0, maxLines), `… +${lines.length - maxLines} lines`].join('\n');
		}
		return lines.join('\n');
	},

	getActivityDescription(input?: Record<string, unknown>): string | null {
		if (!input?.command) return 'Running command';
		const cmd = String(input.command);
		if (cmd.length > 40) {
			return `Running ${cmd.slice(0, 40)}…`;
		}
		return `Running ${cmd}`;
	},
};

/** PowerShell 使用相同的渲染逻辑，名称不同 */
export const powershellTool: Tool = {
	...bashTool,
	name: 'powershell',
	displayName(): string {
		return 'PowerShell';
	},
};
