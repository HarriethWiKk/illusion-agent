/**
 * @fileoverview 侧问（btw）回复显示面板
 *
 * 在 busy 模式下展示助手对侧问的回复，特性：
 * - 竖杠（▎）作为左侧视觉前缀，每行一条
 * - 长行按终端宽度自动换行（soft wrap），续行同样带 ▎ 前缀
 * - 最多显示 10 行，超出部分通过上下箭头翻页
 * - 翻页时首/末行前缀变为 ↑/↓ 提示还有更多内容
 * - 回复使用 illusionShimmer 色，错误使用 error 色
 * - loading 时复用 Spinner 的动词轮换效果
 * - Esc 关闭面板
 *
 * @module BtwPanel
 */

import React, {useState} from 'react';
import {Box, Text, useInput} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';
import {useTerminalSize} from '../hooks/useTerminalSize.js';
import {UiLanguage} from '../i18n.js';
import {wrapToDisplayWidth, WIDTH_SAFETY_EXTRA} from '../utils/markdown.js';
import {Spinner} from './Spinner.js';

/** 单次最多展示的回复行数 */
const MAX_LINES = 10;

/**
 * 侧问回复面板属性
 */
interface BtwPanelProps {
	/** 助手回复文本（多行），无回复时为 null */
	reply: string | null;
	/** 错误文本，无错误时为 null */
	error: string | null;
	/** 是否正在等待回复 */
	loading: boolean;
	/** 当前 UI 语言 */
	language: UiLanguage;
	/** 关闭面板回调（Esc 触发） */
	onDismiss: () => void;
}

/**
 * 侧问回复面板组件
 *
 * @param props - 组件属性
 * @returns 返回面板的 JSX 元素
 */
export function BtwPanel({reply, error, loading, language, onDismiss}: BtwPanelProps): React.JSX.Element {
	const theme = useTheme();
	const {columns: terminalWidth} = useTerminalSize();
	const [offset, setOffset] = useState(0);

	const text = reply ?? error ?? '';
	// 前缀宽度：▎（1 列）+ 空格（1 列）= 2 列；按此宽度换行而非截断
	const contentWidth = Math.max(10, terminalWidth - 2 - WIDTH_SAFETY_EXTRA);
	const lines = wrapToDisplayWidth(text, contentWidth);
	const visibleLines = lines.slice(offset, offset + MAX_LINES);
	const hasMoreAbove = offset > 0;
	const hasMoreBelow = offset + MAX_LINES < lines.length;

	useInput((_input, key) => {
		if (key.escape) {
			onDismiss();
			return;
		}
		if (key.upArrow) {
			setOffset((o) => Math.max(0, o - MAX_LINES));
			return;
		}
		if (key.downArrow) {
			setOffset((o) => Math.min(Math.max(0, lines.length - MAX_LINES), o + MAX_LINES));
			return;
		}
	});

	if (loading) {
		// 不传 label，让 Spinner 轮换 spinnerVerbs，与主对话思考态视觉一致
		return <Spinner language={language} />;
	}

	const lineColor = error ? theme.colors.error : theme.colors.illusionShimmer;

	return (
		<Box flexDirection="column">
			{visibleLines.map((line, i) => {
				// 导航提示放在左侧 ▎ 列：首行上方有更多则显示 ↑，末行下方有更多则显示 ↓
				let prefix = '▎';
				if (i === 0 && hasMoreAbove) {
					prefix = '↑';
				} else if (i === visibleLines.length - 1 && hasMoreBelow) {
					prefix = '↓';
				}
				return (
					<Box key={i}>
						<Text color={lineColor}>{prefix} </Text>
						<Text color={lineColor}>{line}</Text>
					</Box>
				);
			})}
		</Box>
	);
}
