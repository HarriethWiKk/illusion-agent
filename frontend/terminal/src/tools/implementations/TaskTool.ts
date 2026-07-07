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

export const taskOutputTool = noArgsTool('task_output', 'Task Output');
export const taskStopTool = noArgsTool('task_stop', 'Stop Task');
