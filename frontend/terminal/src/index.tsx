/**
 * @fileoverview 终端前端应用入口模块
 *
 * 本模块是 IllusionCode 终端前端的入口点，负责：
 * 1. 从环境变量解析前端配置
 * 2. 设置进程退出时的光标恢复
 * 3. 抑制终端 resize 事件以避免 Ink 组件闪烁
 * 4. 渲染根组件 App
 *
 * @module index
 */

import React from 'react';
import {render} from 'ink';

import {App} from './App.js';
import type {FrontendConfig} from './types.js';

/**
 * 从前端配置环境变量中解析配置对象
 * 如果环境变量不存在，则使用空对象作为默认值
 */
const config = JSON.parse(process.env.ILLUSION_FRONTEND_CONFIG ?? '{}') as FrontendConfig;

/**
 * 恢复终端光标可见性
 *
 * Ink 框架在启动时会隐藏终端光标，此函数在进程退出时恢复光标显示。
 * 通过写入 ANSI 转义序列来实现光标恢复。
 */
const restoreCursor = (): void => {
	process.stdout.write('\x1B[?25h');
};
process.on('exit', restoreCursor);
// SIGINT 由 App 组件中的 useInput 处理，不再强制退出
// 仅在无法恢复时作为安全网退出
process.on('SIGTERM', () => {
	restoreCursor();
	process.exit(143);
});

/**
 * 抑制终端 resize 事件
 *
 * Ink 的 eraseLines(N) + 输出模式在每次 resize 时会导致可见的闪烁。
 * 但 Ink 在每次 React 重新渲染时都会重新计算布局（读取 stdout.columns），
 * 而不仅仅是在 resize 事件时。因此我们可以安全地完全抑制 resize 事件。
 *
 * 布局在以下情况下仍会正确更新：
 * - 用户输入时（PromptInput 状态变化 → React 重新渲染 → 布局重新计算）
 * - 忙碌状态下 Spinner 滴答时（32ms 间隔 → React 重新渲染）
 * - 后端发送事件时（状态变化 → React 重新渲染）
 *
 * 唯一的影响：终端内容在 resize 时不会重新流动，直到下一次 React 重新渲染。
 * 这是可以接受的，因为空闲内容（StatusBar、提示信息）很短，
 * 会在下一次用户交互时重新流动。
 */
const _origEmit = process.stdout.emit.bind(process.stdout);
process.stdout.emit = function (event: string, ...args: unknown[]) {
	if (event === 'resize') {
		return false;
	}
	return _origEmit(event, ...args);
} as typeof process.stdout.emit;

/**
 * 渲染应用根组件
 *
 * 使用 Ink 的 render 函数将 App 组件渲染到终端。
 * 配置对象通过 props 传递给 App 组件。
 */
render(<App config={config} />);
