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
	renderToolResultMessage(_result: string, _input?: Record<string, unknown>, _isBrief?: boolean, structuredOutput?: Record<string, unknown>): string {
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
