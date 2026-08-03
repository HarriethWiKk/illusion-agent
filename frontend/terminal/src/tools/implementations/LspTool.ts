/**
 * @fileoverview LSP 工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

const LSP_LABELS: Record<string, string> = {
	goToDefinition: 'definitions', findReferences: 'references', hover: 'hover info',
	goToImplementation: 'implementations', workspaceSymbol: 'symbols', documentSymbol: 'symbols',
	prepareCallHierarchy: 'call hierarchy items', incomingCalls: 'incoming calls', outgoingCalls: 'outgoing calls',
};

export const lspTool: Tool = {
	name: 'lsp',
	displayName: () => 'LSP',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input) return '';
		const op = String(input.operation ?? '');
		const file = String(input.file ?? input.filePath ?? '');
		const symbol = input.symbol ? String(input.symbol) : '';
		if (symbol && file) return `operation: "${op}", symbol: "${symbol}", in: "${file}"`;
		if (file) return `operation: "${op}", file: "${file}"`;
		return op;
	},
	renderToolResultMessage(result: string, _input?: Record<string, unknown>, _isBrief?: boolean, structuredOutput?: Record<string, unknown>): string {
		// 优先使用 lsp_formatters 格式化的多行文本（含数量、文件分组等完整信息）
		if (result && result.trim() !== '') {
			return result;
		}
		// 回退：无结果文本时用 structured_output 生成摘要
		const metadata = structuredOutput as Record<string, unknown> | undefined;
		const operation = metadata?.operation ?? 'result';
		const resultCount = metadata?.result_count;
		const fileCount = metadata?.file_count;
		const label = LSP_LABELS[String(operation)] ?? 'results';
		const countStr = resultCount !== undefined ? `${resultCount} ` : '';
		const acrossStr = fileCount && Number(fileCount) > 1 ? ` across ${fileCount} files` : '';
		return `Found ${countStr}${label}${acrossStr}`;
	},
	getActivityDescription(): string | null { return 'LSP operation'; },
};
