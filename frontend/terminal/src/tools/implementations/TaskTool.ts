/**
 * @fileoverview 任务管理工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

const noArgsTool = (name: string, displayName: string): Tool => ({
	name,
	displayName: () => displayName,
	renderToolUseMessage: () => '',
	renderToolResultMessage: (result: string) => result.split('\n').find((l) => l.trim()) ?? '(Done)',
});

export const taskCreateTool: Tool = {
	...noArgsTool('task_create', 'TaskCreate'),
	renderToolResultMessage(result: string, input?: Record<string, unknown>): string {
		const desc = input?.subject ?? input?.description ?? '';
		if (desc) return `Task created: ${desc}`;
		return result.split('\n').find((l) => l.trim()) ?? 'Task created';
	},
};

export const taskUpdateTool: Tool = {
	...noArgsTool('task_update', 'TaskUpdate'),
	renderToolResultMessage(result: string, input?: Record<string, unknown>): string {
		const taskId = input?.taskId ?? input?.task_id ?? '';
		const status = input?.status ?? '';
		if (taskId && status) return `Task #${taskId} → ${status}`;
		return result.split('\n').find((l) => l.trim()) ?? 'Updated';
	},
};

export const taskGetTool = noArgsTool('task_get', 'TaskGet');
export const taskListTool = noArgsTool('task_list', 'TaskList');
export const taskOutputTool = noArgsTool('task_output', 'Task Output');
export const taskStopTool = noArgsTool('task_stop', 'Stop Task');
