/**
 * @fileoverview 加载动画组件
 *
 * 显示带有动态效果的加载指示器，包括：
 * - 涟漪图标动画
 * - 动词轮换显示
 * - 省略号呼吸动画
 * - 待办事项进度显示
 *
 * @module Spinner
 */

import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text} from 'ink';

import type {UiLanguage} from '../i18n.js';
import {t} from '../i18n.js';
import {useTheme} from '../theme/ThemeContext.js';
import type {TodoItemSnapshot} from '../types.js';

/**
 * 加载动画组件
 *
 * 在等待后端响应时显示动态加载指示器。
 *
 * @param props - 组件属性
 * @param props.label - 自定义标签文本（可选）
 * @param props.todoItems - 待办事项列表（可选）
 * @param props.language - 当前 UI 语言（可选）
 * @param props.toolName - 当前工具名称（可选）
 * @param props.sessionId - 会话 ID（可选）
 * @returns 返回加载动画的 JSX 元素
 */
export function Spinner({label, todoItems, language, toolName, sessionId}: {label?: string; todoItems?: TodoItemSnapshot[]; language?: UiLanguage; toolName?: string; sessionId?: string}): React.JSX.Element {
	const theme = useTheme();
	const frames = theme.icons.spinner;
	const [frame, setFrame] = useState(0);
	const [verbIndex, setVerbIndex] = useState(0);
	const [dotCount, setDotCount] = useState(0);

	// 从 i18n 获取动词列表
	const verbs = useMemo(() => {
		if (!language) return ['Thinking'];
		return t(language, 'spinnerVerbs').split(',');
	}, [language]);

	// 涟漪图标轮换
	useEffect(() => {
		const timer = setInterval(() => {
			setFrame((f) => (f + 1) % frames.length);
		}, 220);
		return () => clearInterval(timer);
	}, [frames.length]);

	// 动词轮换
	useEffect(() => {
		const timer = setInterval(() => {
			setVerbIndex((v) => (v + 1) % verbs.length);
		}, 3000);
		return () => clearInterval(timer);
	}, [verbs.length]);

	// 省略号呼吸动画：· → ·· → ··· → (空) → ·
	useEffect(() => {
		const timer = setInterval(() => {
			setDotCount((d) => (d + 1) % 4);
		}, 800);
		return () => clearInterval(timer);
	}, []);

	// 从todo列表中获取当前in_progress任务的activeForm
	const currentTodo = todoItems?.find((t) => t.status === 'in_progress');
	const nextTodo = todoItems?.find((t) => t.status === 'pending');

	// 构建显示文本：优先使用 label，其次使用 todo activeForm，再次使用工具名，最后轮换动词
	const verb = label ?? (currentTodo?.activeForm
		? currentTodo.activeForm
		: toolName && language
			? `${t(language, 'spinnerToolAction')} ${toolName}`
			: verbs[verbIndex]);
	const dots = dotCount > 0 ? '·'.repeat(dotCount) : '';

	return (
		<Box flexDirection="column">
			<Box>
				<Box width={2}>
					<Text color={theme.colors.illusionShimmer}>{frames[frame]}</Text>
				</Box>
				<Text color={theme.colors.illusionShimmer}>{verb}</Text>
				<Box width={5}>
					<Text color={theme.colors.illusionShimmer}> {dots}</Text>
				</Box>
				{sessionId ? <Text color={theme.colors.muted} dimColor>(SESSION ID = {sessionId})</Text> : null}
			</Box>
			{nextTodo && !currentTodo ? (
				<Box marginTop={1} marginLeft={3}>
					<Text dimColor>Next: {nextTodo.content}</Text>
				</Box>
			) : null}
		</Box>
	);
}
