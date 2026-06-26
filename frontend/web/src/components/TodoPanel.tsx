/**
 * @fileoverview 待办事项面板组件
 *
 * Web 前端的待办事项面板组件，支持：
 * - 任务状态显示（进行中、待处理、已完成）
 * - 自动排序（进行中 > 待处理 > 已完成）
 * - 折叠/展开功能
 * - 所有任务完成后自动隐藏
 *
 * @module TodoPanel
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { TodoItemSnapshot } from '../types/protocol';

/** 所有任务完成后自动隐藏的延迟时间（毫秒） */
const HIDE_DELAY_MS = 4000;

/**
 * TodoPanel 组件属性接口
 */
interface TodoPanelProps {
  /** 待办事项列表 */
  items: TodoItemSnapshot[];
}

/**
 * 待办事项面板组件
 *
 * Web 前端的待办事项面板组件。
 *
 * @param props - 组件属性
 * @returns 返回待办事项面板的 JSX 元素
 */
export default function TodoPanel({ items }: TodoPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [hidden, setHidden] = useState(false);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 排序：in_progress > pending > completed
  const sorted = useMemo(() => {
    const order: Record<string, number> = { in_progress: 0, pending: 1, completed: 2 };
    return [...items].sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3));
  }, [items]);

  const done = sorted.filter((i) => i.status === 'completed').length;
  const total = sorted.length;
  const allDone = total > 0 && done === total;

  // 找到当前活跃任务用于折叠态预览
  const activeItem = useMemo(() => {
    return sorted.find((i) => i.status === 'in_progress')
      ?? sorted.find((i) => i.status === 'pending')
      ?? [...sorted].reverse().find((i) => i.status === 'completed')
      ?? sorted[0]
      ?? null;
  }, [sorted]);

  // 自动隐藏：全部完成后折叠，延迟后隐藏
  useEffect(() => {
    if (allDone) {
      setCollapsed(true);
      hideTimerRef.current = setTimeout(() => setHidden(true), HIDE_DELAY_MS);
    } else {
      setHidden(false);
      if (hideTimerRef.current) { clearTimeout(hideTimerRef.current); hideTimerRef.current = null; }
    }
    return () => { if (hideTimerRef.current) clearTimeout(hideTimerRef.current); };
  }, [sorted, allDone]);

  if (sorted.length === 0 || hidden) return null;

  return (
    <div className="mb-4 rounded-xl glass-surface overflow-hidden">
      {/* 头部 */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full px-4 py-2.5 flex items-center gap-3 glass-option-hover transition-colors cursor-pointer"
      >
        {/* 进度计数 */}
        <span className="text-xs font-mono text-content-secondary tabular-nums shrink-0">
          <span className="text-content-primary font-medium">{done}</span>
          <span className="mx-0.5">/</span>
          <span>{total}</span>
        </span>

        {/* 折叠态：显示活跃任务预览 */}
        {collapsed && activeItem && (
          <span className="flex-1 text-xs text-content-secondary truncate text-left min-w-0">
            {activeItem.activeForm && activeItem.status === 'in_progress'
              ? activeItem.activeForm
              : activeItem.content}
          </span>
        )}

        {/* 展开态占位 */}
        {!collapsed && <span className="flex-1" />}

        {/* 折叠箭头 */}
        <svg
          className={`w-3.5 h-3.5 text-content-disabled shrink-0 transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`}
          viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>

      {/* 任务列表 */}
      {!collapsed && (
        <div className="px-3 pb-3 flex flex-col gap-0.5 max-h-40 overflow-y-auto">
          {sorted.map((item, idx) => (
            <TodoRow key={`${item.content}-${idx}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function TodoRow({ item }: { item: TodoItemSnapshot }) {
  const status = item.status;

  return (
    <div className="flex items-start gap-2.5 px-2 py-1.5 rounded-md group">
      {/* 状态图标 */}
      <div className="mt-0.5 shrink-0 w-4 h-4 flex items-center justify-center">
        {status === 'completed' && (
          <svg className="w-4 h-4 text-green-500" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 8.5l3.5 3.5 6.5-8" />
          </svg>
        )}
        {status === 'in_progress' && (
          <span className="w-3 h-3 rounded-full bg-primary animate-pulse-scale" />
        )}
        {status === 'pending' && (
          <span className="w-3 h-3 rounded-full border-2 border-border-light bg-white" />
        )}
      </div>

      {/* 文本 */}
      <span
        className={`text-sm leading-relaxed flex-1 min-w-0 transition-colors duration-200 ${
          status === 'completed'
            ? 'text-content-disabled line-through'
            : status === 'in_progress'
            ? 'text-content-primary font-medium'
            : 'text-content-secondary'
        }`}
      >
        {item.activeForm && status === 'in_progress' ? item.activeForm : item.content}
      </span>
    </div>
  );
}
