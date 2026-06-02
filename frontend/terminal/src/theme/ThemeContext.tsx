/**
 * @fileoverview 主题上下文模块
 *
 * 提供 React 主题上下文，用于在整个应用中共享主题配置。
 *
 * @module ThemeContext
 */

import React, {createContext, useContext} from 'react';

import {type ThemeConfig, defaultTheme} from './builtinThemes.js';

/** 重新导出主题配置类型 */
export type {ThemeConfig};

/**
 * 主题上下文
 *
 * 创建主题上下文，使用默认主题作为初始值。
 */
const ThemeContext = createContext<ThemeConfig>(defaultTheme);

/**
 * 主题提供者组件
 *
 * 包裹子组件并提供主题上下文。目前使用默认主题。
 *
 * @param props - 组件属性
 * @param props.children - 子组件
 * @returns 返回包含主题上下文的 JSX 元素
 */
export function ThemeProvider({children}: {children: React.ReactNode}): React.JSX.Element {
	return (
		<ThemeContext.Provider value={defaultTheme}>
			{children}
		</ThemeContext.Provider>
	);
}

/**
 * 主题 Hook
 *
 * 获取当前主题配置。必须在 ThemeProvider 内部使用。
 *
 * @returns 当前主题配置对象
 */
export function useTheme(): ThemeConfig {
	return useContext(ThemeContext);
}
