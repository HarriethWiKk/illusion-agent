/**
 * @fileoverview 内置主题配置模块
 *
 * 定义应用的主题配置类型和默认主题。
 * 主题包含颜色方案和图标集两部分。
 *
 * @module builtinThemes
 */

/**
 * 主题配置类型
 *
 * 定义应用的视觉风格，包括颜色和图标。
 */
export type ThemeConfig = {
	/** 主题名称 */
	name: string;
	/** 颜色配置 */
	colors: {
		/** 主色调 */
		primary: string;
		/** 次要色调 */
		secondary: string;
		/** 强调色 */
		accent: string;
		/** 前景色（文本） */
		foreground: string;
		/** 背景色 */
		background: string;
		/** 柔和色（次要信息） */
		muted: string;
		/** 成功色 */
		success: string;
		/** 警告色 */
		warning: string;
		/** 错误色 */
		error: string;
		/** 信息色 */
		info: string;
		/** Illusion 品牌色 */
		illusion: string;
		/** Illusion 闪烁色 */
		illusionShimmer: string;
		/** 文本色 */
		text: string;
		/** 微妙色 */
		subtle: string;
		/** 高亮色 */
		highlight: string;
		/** 提示边框色 */
		promptBorder: string;
		/** 建议色 */
		suggestion: string;
		/** 权限色 */
		permission: string;
	};
	/** 图标配置 */
	icons: {
		/** 加载动画帧 */
		spinner: string[];
		/** 工具图标 */
		tool: string;
		/** 助手图标 */
		assistant: string;
		/** 用户图标 */
		user: string;
		/** 系统图标 */
		system: string;
		/** 成功图标 */
		success: string;
		/** 错误图标 */
		error: string;
		/** 待处理图标 */
		pending: string;
		/** 进行中图标 */
		inProgress: string;
		/** 已完成图标 */
		completed: string;
		/** 列表项图标 */
		bullet: string;
		/** 箭头图标 */
		arrow: string;
		/** 勾选图标 */
		check: string;
		/** 叉号图标 */
		cross: string;
		/** 展开图标 */
		chevron: string;
		/** 圆点图标 */
		dot: string;
		/** 指针图标 */
		pointer: string;
		/** 中间点图标 */
		middleDot: string;
		/** 结果前缀图标 */
		resultPrefix: string;
	};
};

/**
 * 默认主题配置
 *
 * 应用启动时使用的默认主题，采用深色背景配明亮色调的风格。
 */
export const defaultTheme: ThemeConfig = {
	name: 'default',
	colors: {
		primary: '#56d4dd',
		secondary: 'white',
		accent: 'magenta',
		foreground: 'white',
		background: 'black',
		muted: '#9ca3af',
		success: 'green',
		warning: 'yellow',
		error: 'red',
		info: '#89ddff',
		illusion: '#f0c8b0',
		illusionShimmer: '#e07070',
		text: 'white',
		subtle: '#a8b2c1',
		highlight: '#56d4dd',
		promptBorder: '#8b949e',
		suggestion: '#89ddff',
		permission: '#bb9af7',
	},
	icons: {
		spinner: ['·', '◌', '◎', '◌'],
		tool: '●',
		assistant: '●',
		user: '❯',
		system: '✻',
		success: '✓',
		error: '✗',
		pending: '○',
		inProgress: '◐',
		completed: '●',
		bullet: '•',
		arrow: '→',
		check: '✓',
		cross: '✗',
		chevron: '›',
		dot: '●',
		pointer: '❯',
		middleDot: '·',
		resultPrefix: '⎿',
	},
};
