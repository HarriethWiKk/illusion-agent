/**
 * @fileoverview 主题（浅色/深色/跟随系统）管理 Hook
 *
 * 主题来源与持久化均基于后端 settings.json 的 theme 字段，不再使用浏览器 localStorage：
 * - 初始加载：通过 GET /api/settings 读取 theme 字段（light / dark / system）
 * - 切换主题：通过 PATCH /api/settings/theme 同步写入 settings.json
 * - 跟随系统：当 theme === 'system' 时，根据 prefers-color-scheme 决定实际深浅
 * - 通过在 `<html>` 上添加/移除 `dark` 类切换主题（配合 :root.dark CSS 变量）
 *
 * 该字段仅用于 web 前端，不传递到 terminal 端（terminal 无主题系统）。
 *
 * @module useTheme
 */

import { useCallback, useEffect, useState } from 'react';
import { settingsApi } from '../api';

/** 主题模式：浅色 / 深色 / 跟随系统 */
export type Theme = 'light' | 'dark' | 'system';
/** 实际生效的深浅主题（system 已解析为 light/dark） */
type ResolvedTheme = 'light' | 'dark';

/** 读取系统深色偏好 */
function readSystemTheme(): ResolvedTheme {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

/** 将主题模式解析为实际深浅主题 */
function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === 'system' ? readSystemTheme() : theme;
}

/** 应用主题到 <html> 根节点 */
function applyTheme(resolved: ResolvedTheme) {
  const root = document.documentElement;
  if (resolved === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

/**
 * 主题管理 Hook
 *
 * @returns { theme, resolved, toggleTheme, setTheme }
 *  - theme: 当前主题模式（light / dark / system）
 *  - resolved: 实际生效的深浅主题（system 已解析）
 *  - toggleTheme: 三态循环切换（light → dark → system → light）
 *  - setTheme: 直接设置主题模式
 */
export function useTheme() {
  // 初始值默认 light（与 settings.json 默认值一致），待 API 返回后校正
  const [theme, setThemeState] = useState<Theme>('light');
  // 实际应用的主题（light/dark），system 模式下跟随系统偏好
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme('light'));

  // 初始加载：从 settings.json 读取 theme 字段
  useEffect(() => {
    let cancelled = false;
    settingsApi
      .get()
      .then((resp) => {
        if (cancelled) return;
        setThemeState(resp.theme);
        setResolved(resolveTheme(resp.theme));
      })
      .catch(() => {
        // 读取失败时保留默认值 light
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // 应用到 DOM
  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // 监听系统主题变化：仅当 theme === 'system' 时跟随
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (theme === 'system') {
        setResolved(e.matches ? 'dark' : 'light');
      }
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [theme]);

  /** 设置主题模式并同步写入 settings.json */
  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    setResolved(resolveTheme(next));
    // 同步到 settings.json（失败忽略，不阻塞 UI）
    settingsApi.updateTheme(next).catch(() => {
      // 写入失败时不回滚 UI 状态，下次加载会从 settings.json 重新读取
    });
  }, []);

  /** 三态循环切换：light → dark → system → light */
  const toggleTheme = useCallback(() => {
    const order: Theme[] = ['light', 'dark', 'system'];
    const idx = order.indexOf(theme);
    // theme 必在 order 中，idx 不为 -1，取模结果必存在
    const next = order[(idx + 1) % order.length];
    if (next) setTheme(next);
  }, [theme, setTheme]);

  return { theme, resolved, toggleTheme, setTheme };
}
