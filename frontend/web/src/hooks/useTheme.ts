/**
 * @fileoverview 主题（深色/浅色）管理 Hook
 *
 * 提供深色模式的切换、持久化与系统偏好跟随。
 * - 首次访问：跟随 `prefers-color-scheme`
 * - 用户切换后：写入 localStorage，覆盖系统偏好
 * - 通过在 `<html>` 上添加/移除 `dark` 类切换主题（配合 :root.dark CSS 变量）
 *
 * @module useTheme
 */

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'illusion-theme';

/** 读取 localStorage 中保存的主题（无记录返回 null 以便回退到系统偏好） */
function readStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'light' || v === 'dark') return v;
  } catch {
    // localStorage 不可用（隐私模式等），忽略
  }
  return null;
}

/** 读取系统深色偏好 */
function readSystemTheme(): Theme {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

/** 应用主题到 <html> 根节点 */
function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

/**
 * 主题管理 Hook
 *
 * @returns { theme, toggleTheme, setTheme }
 */
export function useTheme() {
  // 初始值：localStorage > 系统偏好
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme() ?? readSystemTheme());

  // 应用到 DOM + 持久化
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // 监听系统主题变化：仅当用户未显式选择时跟随
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      // 仅在没有用户显式选择时跟随系统
      if (readStoredTheme() === null) {
        setThemeState(e.matches ? 'dark' : 'light');
      }
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  const setTheme = useCallback((next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // 忽略写入失败
    }
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  }, [theme, setTheme]);

  return { theme, toggleTheme, setTheme };
}
