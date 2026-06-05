/**
 * @fileoverview 全局动画帧管理器 Hook
 *
 * 提供共享的动画时钟，所有闪烁指示器从同一时钟派生状态，
 * 保证同频同步。Ink 终端环境使用 setInterval 实现。
 *
 * @module hooks/useAnimationFrame
 */

import {useEffect, useState} from 'react';

/**
 * 全局共享的动画时钟
 * 所有 useBlink 从此时钟派生，保证同步
 */
let globalTimestamp = 0;
let globalListeners: Set<() => void> = new Set();
let globalInterval: ReturnType<typeof setInterval> | null = null;
let globalRefCount = 0;

const GLOBAL_INTERVAL_MS = 300; // 300ms 更新一次（与闪烁周期 600ms 匹配）

function startGlobalClock(): void {
	if (globalInterval) return;
	globalInterval = setInterval(() => {
		globalTimestamp = Date.now();
		globalListeners.forEach((listener) => listener());
	}, GLOBAL_INTERVAL_MS);
}

function stopGlobalClock(): void {
	if (globalInterval) {
		clearInterval(globalInterval);
		globalInterval = null;
	}
}

/**
 * 订阅全局动画时钟
 *
 * @returns 当前时间戳
 */
export function useGlobalAnimationClock(): number {
	const [timestamp, setTimestamp] = useState(globalTimestamp);

	useEffect(() => {
		globalRefCount++;
		startGlobalClock();

		const listener = () => setTimestamp(globalTimestamp);
		globalListeners.add(listener);

		return () => {
			globalListeners.delete(listener);
			globalRefCount--;
			if (globalRefCount === 0) {
				stopGlobalClock();
			}
		};
	}, []);

	return timestamp;
}
