/**
 * @fileoverview Goal 工具渲染实现（get_goal / create_goal / update_goal）
 *
 * 三个 goal 工具共享统一的 GOAL_OUTPUT JSON 输出，本渲染器将其解析为
 * 人类可读的摘要（目标 / 相位 / 轮次 / 激活状态），替代原始 JSON 回退。
 *
 * @module tools/implementations/GoalTool
 */

import type {Tool} from '../ToolInterface.js';

/** 目标文本在摘要中的截断长度 */
const OBJECTIVE_MAX_CHARS = 60;

/** 解析后的 goal 字段（与后端 goal_value / status_payload 对齐） */
interface GoalFields {
	objective?: unknown;
	phase?: unknown;
	roundsStarted?: unknown;
	maxGoalRounds?: unknown;
	blockedReason?: {code?: string; message?: string} | null;
}

function truncate(text: string, max: number): string {
	return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** 解析 GOAL_OUTPUT 的 goal 对象；不可解析或无目标时返回 null */
function parseGoal(result: string): GoalFields | null {
	let data: unknown;
	try {
		data = JSON.parse(result);
	} catch {
		return null;
	}
	if (typeof data !== 'object' || data === null) return null;
	const goal = (data as Record<string, unknown>).goal;
	if (typeof goal !== 'object' || goal === null) return null;
	return goal as GoalFields;
}

/** 生成目标状态摘要（相位 + 轮次 + 激活，可带受阻原因） */
function renderGoalSummary(goal: GoalFields): string {
	const phase = String(goal.phase ?? 'unknown');
	const round = String(goal.roundsStarted ?? '?');
	const max = String(goal.maxGoalRounds ?? '?');
	let summary = `Phase: ${phase} · Round ${round}/${max}`;
	const blocked = goal.blockedReason;
	if (blocked && blocked.message) {
		summary += ` · Blocked: ${truncate(blocked.message, OBJECTIVE_MAX_CHARS)}`;
	}
	return summary;
}

function renderGoalResult(result: string): string {
	const goal = parseGoal(result);
	if (!goal) {
		// 非 JSON（错误消息等）回退到首行
		return result.split('\n').find((l) => l.trim()) ?? '(No output)';
	}
	const objective = String(goal.objective ?? '');
	if (!objective) {
		return 'No goal set';
	}
	return `Objective: ${truncate(objective, OBJECTIVE_MAX_CHARS)}\n${renderGoalSummary(goal)}`;
}

export const getGoalTool: Tool = {
	name: 'get_goal',
	displayName: () => 'GetGoal',
	renderToolUseMessage: () => '',
	renderToolResultMessage: renderGoalResult,
	getActivityDescription: () => 'Reading goal',
};

export const createGoalTool: Tool = {
	name: 'create_goal',
	displayName: () => 'CreateGoal',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.objective) return '';
		return truncate(String(input.objective), OBJECTIVE_MAX_CHARS);
	},
	renderToolResultMessage(result: string): string {
		const goal = parseGoal(result);
		if (!goal) {
			return result.split('\n').find((l) => l.trim()) ?? '(Done)';
		}
		const objective = String(goal.objective ?? '');
		return objective
			? `Goal set: ${truncate(objective, OBJECTIVE_MAX_CHARS)}\n${renderGoalSummary(goal)}`
			: renderGoalSummary(goal);
	},
	getActivityDescription(input?: Record<string, unknown>): string | null {
		return input?.objective ? truncate(String(input.objective), OBJECTIVE_MAX_CHARS) : 'Creating goal';
	},
};

export const updateGoalTool: Tool = {
	name: 'update_goal',
	displayName: () => 'UpdateGoal',
	renderToolUseMessage(input?: Record<string, unknown>): string {
		if (!input?.action) return '';
		const action = String(input.action);
		if (action === 'edit' && input.objective) {
			return `edit ${truncate(String(input.objective), OBJECTIVE_MAX_CHARS)}`;
		}
		return action;
	},
	renderToolResultMessage: renderGoalResult,
	getActivityDescription(input?: Record<string, unknown>): string | null {
		return input?.action ? String(input.action) : 'Updating goal';
	},
};
