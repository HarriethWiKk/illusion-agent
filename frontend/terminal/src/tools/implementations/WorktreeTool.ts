/**
 * @fileoverview 工作树工具渲染实现
 */
import type {Tool} from '../ToolInterface.js';

export const enterWorktreeTool: Tool = {
	name: 'enter_worktree',
	displayName: () => 'EnterWorktree',
	renderToolUseMessage: () => 'Creating worktree…',
	renderToolResultMessage: (result: string) => result.split('\n').find((l) => l.trim()) ?? 'Switched to worktree',
};

export const exitWorktreeTool: Tool = {
	name: 'exit_worktree',
	displayName: () => 'ExitWorktree',
	renderToolUseMessage: () => 'Exiting worktree…',
	renderToolResultMessage: (result: string) => result.split('\n').find((l) => l.trim()) ?? 'Exited worktree',
};
