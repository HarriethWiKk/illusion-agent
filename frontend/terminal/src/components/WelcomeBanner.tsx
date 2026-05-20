import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

// prettier-ignore
const LOGO = [
	'████╗██╗  ██╗  ██╗ ██╗██████╗████╗  ████╗  ███╗  ██╗',
	'╚██╔╝██║  ██║  ██║ ██║██╔═══╝╚██╔╝██║   ██║████╗ ██║',
	' ██║ ██║  ██║  ██║ ██║██████╗ ██║ ██║   ██║██║██╗██║',
	' ██║ ██║  ██║  ██║ ██║╚═══██║ ██║ ██║   ██║██║╚████║',
	'████╗████╗████╗ ████╔╝██████║████╗  ████╔╝ ██║ ╚═██║',
	'╚═══╝╚═══╝╚═══╝ ╚═══╝ ╚═════╝╚═══╝  ╚═══╝  ╚═╝   ╚═╝',
];

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
				<Text color={theme.colors.illusion} bold>{'  Illusion Code · AI Coding Assistant'}</Text>
			</Box>
			<Box marginTop={1} flexDirection="column">
				<Box>
					<Text dimColor>{`  ${theme.icons.pointer} `}</Text>
					<Text color={theme.colors.subtle}>/help</Text>
					<Text dimColor>{' view all commands'}</Text>
				</Box>
				<Box>
					<Text dimColor>{`  ${theme.icons.pointer} `}</Text>
					<Text color={theme.colors.subtle}>/model</Text>
					<Text dimColor>{' switch model'}</Text>
				</Box>
				<Box>
					<Text dimColor>{`  ${theme.icons.pointer} `}</Text>
					<Text color={theme.colors.subtle}>/resume</Text>
					<Text dimColor>{' resume session'}</Text>
				</Box>
				<Box>
					<Text dimColor>{`  ${theme.icons.pointer} `}</Text>
					<Text color={theme.colors.subtle}>/language</Text>
					<Text dimColor>{' switch language'}</Text>
				</Box>
			</Box>
		</Box>
	);
}
