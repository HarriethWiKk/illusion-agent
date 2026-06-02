/**
 * @fileoverview 终端尺寸 Hook
 *
 * 提供获取终端窗口尺寸的功能。
 *
 * @module useTerminalSize
 */

import {useStdout} from 'ink';

/**
 * 终端尺寸 Hook
 *
 * 获取当前终端窗口的列数和行数。
 * 如果无法获取标准输出（例如在非终端环境中），则返回默认值 80x24。
 *
 * @returns 包含 columns（列数）和 rows（行数）的对象
 */
export function useTerminalSize(): {columns: number; rows: number} {
	const {stdout} = useStdout();
	return {
		columns: stdout?.columns ?? 80,
		rows: stdout?.rows ?? 24,
	};
}
