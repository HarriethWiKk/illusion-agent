/**
 * @fileoverview 侧边栏组件
 *
 * Web 前端的侧边栏组件，支持：
 * - 折叠/展开功能
 * - 新建会话
 * - 会话列表显示和选择
 * - 删除会话功能
 * - 连接状态显示
 *
 * @module Sidebar
 */

import { useCallback, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

/**
 * Sidebar 组件属性接口
 */
interface SidebarProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 是否已连接 */
  connected: boolean;
  /** 会话列表 */
  sessions: { value: string; label: string }[];
  /** 新建会话回调 */
  onNewSession: () => void;
  /** 选择会话回调 */
  onSelectSession: (sessionId: string) => void;
  /** 列出会话回调 */
  onListSessions: () => void;
  /** 删除会话回调 */
  onDeleteSessions: () => void;
  /** 是否折叠 */
  collapsed: boolean;
  /** 折叠/展开切换回调 */
  onToggle: () => void;
  /** 侧边栏宽度（可选，默认 280） */
  width?: number;
  /** 正在恢复的会话 ID（可选，用于在对应会话项显示加载 spinner） */
  restoringSessionId?: string | null;
  /** 打开设置配置表单回调（点击底部 settings 齿轮图标触发） */
  onOpenSettings: () => void;
}

/**
 * 侧边栏组件
 *
 * Web 前端的侧边栏组件。
 *
 * @param props - 组件属性
 * @returns 返回侧边栏的 JSX 元素
 */
/**
 * 会话列表项（带聚光灯悬停效果和活跃指示条）
 */
function SessionItem({ session, index, isRestoring, onSelect }: {
  session: { value: string; label: string };
  index: number;
  isRestoring: boolean;
  onSelect: (id: string) => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--spotlight-x', `${e.clientX - rect.left}px`);
    el.style.setProperty('--spotlight-y', `${e.clientY - rect.top}px`);
  }, []);

  return (
    <button
      ref={ref}
      onClick={() => onSelect(session.value)}
      onMouseMove={handleMouseMove}
      className="spotlight-hover w-full text-left px-3 py-2.5 rounded-lg text-sm text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer flex items-center gap-2 animate-fade-in-up"
      style={{ animationDelay: `${index * 30}ms` }}
      title={session.label}
    >
      {isRestoring && (
        <svg className="animate-spin w-3.5 h-3.5 text-primary shrink-0" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      <span className="line-clamp-2 leading-relaxed flex-1">{session.label}</span>
    </button>
  );
}

export default function Sidebar({
  lang, connected, sessions, onNewSession, onSelectSession, onListSessions, onDeleteSessions, collapsed, onToggle, width = 280, restoringSessionId, onOpenSettings,
}: SidebarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [listExpanded, setListExpanded] = useState(false);

  if (collapsed) {
    return (
      <div className="w-14 glass-panel border-r border-white/30 flex flex-col items-center py-4 shrink-0 select-none">
        <button
          onClick={onToggle}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer"
          title={t(lang, 'expand_panel')}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 3l5 5-5 5" />
          </svg>
        </button>
        <button
          onClick={onOpenSettings}
          title={t(lang, 'sidebarSettingsTooltip')}
          className="mt-auto w-9 h-9 flex items-center justify-center rounded-lg text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <aside className="glass-panel border-r border-white/30 flex flex-col h-full shrink-0 select-none transition-[width] duration-300 ease-in-out" style={{ width: `${width}px` }}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-border-light">
        <button
          onClick={onToggle}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary hover:text-content-primary glass-option-hover transition-colors cursor-pointer"
          title={t(lang, 'collapse_panel')}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M10 3l-5 5 5 5" />
          </svg>
        </button>
        <span className="font-display font-bold text-content-primary text-sm tracking-wider">{t(lang, 'sidebar_title')}</span>
        <div className="relative" onBlur={(e) => { if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget as Node)) { setMenuOpen(false); } }}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary hover:text-content-primary glass-option-hover transition-colors cursor-pointer"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="8" cy="4" r="1.5" />
              <circle cx="8" cy="8" r="1.5" />
              <circle cx="8" cy="12" r="1.5" />
            </svg>
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-full mt-2 glass-surface rounded-xl z-20 min-w-[180px] overflow-hidden animate-scale-in dropdown-origin-top-left">
                <button
                  onClick={() => { onDeleteSessions(); setMenuOpen(false); }}
                  className="danger-action w-full text-left px-4 py-2.5 text-sm text-danger cursor-pointer flex items-center gap-2.5"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                  {t(lang, 'delete_session')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
      <div className="px-4 py-3">
        <button
          onClick={onNewSession}
          disabled={!connected}
          className="pill-badge w-full text-left px-3 py-2.5 rounded-lg text-sm text-content-primary transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <span className="w-5 h-5 rounded-md bg-primary flex items-center justify-center text-white font-bold text-xs">+</span>
          {t(lang, 'new_session')}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        <div className="py-2 text-[11px] text-content-disabled font-semibold px-1 uppercase tracking-widest">
          {t(lang, 'resume_session')}
        </div>
        {sessions.length > 0 ? (
          <>
            <div className="space-y-0.5">
              {(listExpanded ? sessions : sessions.slice(0, 5)).map((s, idx) => (
                <SessionItem
                  key={s.value}
                  session={s}
                  index={idx}
                  isRestoring={restoringSessionId === s.value}
                  onSelect={onSelectSession}
                />
              ))}
            </div>
            {sessions.length > 5 && (
              <button
                onClick={() => setListExpanded(!listExpanded)}
                className="w-full flex items-center justify-center py-1.5 text-content-disabled hover:text-content-secondary glass-option-hover rounded-lg transition-colors cursor-pointer mt-1"
                title={listExpanded ? t(lang, 'collapse_messages') : t(lang, 'show_earlier').replace('{count}', String(sessions.length - 5))}
              >
                <svg className={`w-3.5 h-3.5 transition-transform duration-150 ${listExpanded ? 'rotate-180' : ''}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 4.5L6 7.5L9 4.5" />
                </svg>
              </button>
            )}
          </>
        ) : (
          <button
            onClick={onListSessions}
            disabled={!connected}
            className="w-full text-left px-3 py-2 rounded-lg text-sm text-content-disabled glass-option-hover hover:text-content-secondary transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t(lang, 'load_more')}
          </button>
        )}
      </div>
      <div className="px-4 py-3 border-t border-border-light">
        <button
          onClick={onOpenSettings}
          title={t(lang, 'sidebarSettingsTooltip')}
          className="w-full flex items-center justify-center gap-2 text-xs text-content-secondary hover:text-content-primary glass-option-hover rounded-lg px-2 py-1.5 transition-colors cursor-pointer"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <span className="text-[11px]">{t(lang, 'settings')}</span>
        </button>
      </div>
    </aside>
  );
}
