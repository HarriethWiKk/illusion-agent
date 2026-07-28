/**
 * @fileoverview 欢迎横幅组件
 *
 * 在会话开始时显示欢迎信息和常用命令提示。
 *
 * @module WelcomeBanner
 */

import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

// prettier-ignore
/** ASCII 艺术 Logo */
const LOGO = [
	'████╗██╗  ██╗  ██╗ ██╗██████╗████╗  ████╗  ███╗  ██╗',
	'╚██╔╝██║  ██║  ██║ ██║██╔═══╝╚██╔╝██║   ██║████╗ ██║',
	' ██║ ██║  ██║  ██║ ██║██████╗ ██║ ██║   ██║██║██╗██║',
	' ██║ ██║  ██║  ██║ ██║╚═══██║ ██║ ██║   ██║██║╚████║',
	'████╗████╗████╗ ████╔╝██████║████╗  ████╔╝ ██║ ╚═██║',
	'╚═══╝╚═══╝╚═══╝ ╚═══╝ ╚═════╝╚═══╝  ╚═══╝  ╚═╝   ╚═╝',
];

/**
 * 欢迎横幅组件
 *
 * 在会话开始时显示应用 Logo 和常用命令提示。
 *
 * @param props - 组件属性
 * @param props.language - 当前 UI 语言（可选）
 * @returns 返回欢迎横幅的 JSX 元素
 */
export function WelcomeBanner({language}: {language?: string}): React.JSX.Element {
	const theme = useTheme();

	return (
		<Box flexDirection="column" marginBottom={1}>
			<Box flexDirection="column">
				{LOGO.map((line, i) => (
					<Text key={i} color={theme.colors.primary} bold>{line}</Text>
				))}
			</Box>
			<Box marginTop={1}>
				<Text color={theme.colors.illusion} bold>{'  Illusion Agent · AI Coding Assistant'}</Text>
			</Box>
			<Box marginTop={1} flexDirection="column">
				<Text dimColor>{`  ${theme.icons.pointer} `}<Text color={theme.colors.suggestion}>/help</Text>{' view all commands'}</Text>
				<Text dimColor>{`  ${theme.icons.pointer} `}<Text color={theme.colors.suggestion}>/model</Text>{' switch model'}</Text>
				<Text dimColor>{`  ${theme.icons.pointer} `}<Text color={theme.colors.suggestion}>/resume</Text>{' resume session'}</Text>
				<Text dimColor>{`  ${theme.icons.pointer} `}<Text color={theme.colors.suggestion}>/language</Text>{' switch language'}</Text>
			</Box>
		</Box>
	);
}
