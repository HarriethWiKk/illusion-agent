/**
 * @fileoverview Token 数字格式化工具
 *
 * 将 token 数量格式化为紧凑表示，便于在状态栏等空间有限的位置展示。
 * 例如：387519 → "387.5k"，1838 → "1.8k"，2000000 → "2.0M"。
 *
 * @module utils/fmtTokens
 */

/**
 * 格式化 token 数字为紧凑表示。
 *
 * - 大于等于 1M 时使用 "X.XM" 格式（如 2.0M）
 * - 大于等于 1k 时使用 "X.Xk" 格式（如 387.5k）
 * - 否则原样输出数字字符串
 *
 * @param n - token 数量
 * @returns 格式化后的字符串
 */
export function fmtTokens(n: number): string {
	if (n >= 1_000_000) {
		return `${(n / 1_000_000).toFixed(1)}M`;
	}
	if (n >= 1_000) {
		return `${(n / 1_000).toFixed(1)}k`;
	}
	return String(n);
}
