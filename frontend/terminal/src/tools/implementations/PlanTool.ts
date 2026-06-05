/**
 * @fileoverview 计划模式工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const enterPlanModeTool: Tool = {
	name: 'enter_plan_mode',
	displayName: () => 'EnterPlanMode',
	renderToolUseMessage: () => '',
	renderToolResultMessage: () => 'Entered plan mode',
};

export const exitPlanModeTool: Tool = {
	name: 'exit_plan_mode',
	displayName: () => 'ExitPlanMode',
	renderToolUseMessage: () => '',
	renderToolResultMessage: (result: string) => {
		if (!result || result.trim() === '') return 'Exited plan mode';
		return result.split('\n').find((l) => l.trim()) ?? 'Exited plan mode';
	},
};
