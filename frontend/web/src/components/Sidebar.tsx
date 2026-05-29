import { useState } from 'react';
import { t, type UiLanguage } from '../i18n';

interface SidebarProps {
  lang: UiLanguage;
  connected: boolean;
  sessions: { value: string; label: string }[];
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onListSessions: () => void;
  onDeleteSessions: () => void;
  collapsed: boolean;
  onToggle: () => void;
  width?: number;
}

export default function Sidebar({
  lang, connected, sessions, onNewSession, onSelectSession, onListSessions, onDeleteSessions, collapsed, onToggle, width = 280,
}: SidebarProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  if (collapsed) {
    return (
      <div className="w-14 bg-surface-card border-r border-border-light flex flex-col items-center py-4 shrink-0 select-none">
        <button
          onClick={onToggle}
          className="w-9 h-9 flex items-center justify-center rounded-lg text-content-secondary hover:bg-surface-hover hover:text-content-primary transition-colors cursor-pointer"
          title="展开侧边栏"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 3l5 5-5 5" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <aside className="bg-surface-card border-r border-border-light flex flex-col h-full shrink-0 select-none" style={{ width: `${width}px` }}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-border-light">
        <button
          onClick={onToggle}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary hover:text-content-primary hover:bg-surface-hover transition-colors cursor-pointer"
          title="收起侧边栏"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M10 3l-5 5 5 5" />
          </svg>
        </button>
        <span className="font-display font-semibold text-content-primary text-sm tracking-wider">{t(lang, 'sidebar_title')}</span>
        <div className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary hover:text-content-primary hover:bg-surface-hover transition-colors cursor-pointer"
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
              <div className="absolute right-0 top-full mt-2 bg-white border border-border-light rounded-xl shadow-lg z-20 min-w-[160px] py-1">
                <button
                  onClick={() => { onDeleteSessions(); setMenuOpen(false); }}
                  className="w-full text-left px-3 py-2 text-sm text-danger hover:bg-red-50 transition-colors cursor-pointer"
                >
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
          className="w-full text-left px-3 py-2 rounded-lg text-sm text-content-primary hover:bg-surface-hover transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 border border-border-light bg-white"
        >
          <span className="w-5 h-5 rounded-md bg-primary flex items-center justify-center text-white font-bold text-xs">+</span>
          {t(lang, 'new_session')}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        <div className="py-2 text-[11px] text-content-secondary font-medium px-1 uppercase tracking-wider">
          {t(lang, 'resume_session')}
        </div>
        {sessions.length > 0 ? (
          <div className="space-y-0.5">
            {sessions.map((s) => (
              <button
                key={s.value}
                onClick={() => onSelectSession(s.value)}
                className="w-full text-left px-3 py-2 rounded-lg text-sm text-content-secondary hover:bg-surface-hover hover:text-content-primary transition-colors cursor-pointer"
                title={s.label}
              >
                <span className="line-clamp-2 leading-relaxed">{s.label}</span>
              </button>
            ))}
          </div>
        ) : (
          <button
            onClick={onListSessions}
            disabled={!connected}
            className="w-full text-left px-3 py-2 rounded-lg text-sm text-content-disabled hover:bg-surface-hover hover:text-content-secondary transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t(lang, 'load_more')}
          </button>
        )}
      </div>
      <div className="px-4 py-3 border-t border-border-light">
        <div className="flex items-center gap-2 text-xs">
          <span className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-content-secondary">{connected ? 'Connected' : t(lang, 'disconnected')}</span>
        </div>
      </div>
    </aside>
  );
}
