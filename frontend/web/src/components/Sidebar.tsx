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
}

export default function Sidebar({
  lang, connected, sessions, onNewSession, onSelectSession, onListSessions, onDeleteSessions, collapsed, onToggle,
}: SidebarProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  if (collapsed) {
    return (
      <div className="w-14 bg-gradient-to-b from-cream-100/80 to-sand-100/80 backdrop-blur-sm border-r border-sand-200/60 flex flex-col items-center py-4 shrink-0 animate-fade-in">
        <button
          onClick={onToggle}
          className="w-9 h-9 flex items-center justify-center rounded-xl text-khaki-500 hover:bg-cream-200/80 hover:text-khaki-700 transition-all duration-200 cursor-pointer text-sm hover:scale-105 active:scale-95"
          title="展开侧边栏"
        >
          ▸
        </button>
      </div>
    );
  }

  return (
    <aside className="w-[280px] bg-gradient-to-b from-cream-100/90 to-sand-100/90 backdrop-blur-sm border-r border-sand-200/60 flex flex-col h-full shrink-0 animate-slide-right">
      <div className="flex items-center justify-between px-5 py-4 border-b border-sand-200/60">
        <button
          onClick={onToggle}
          className="w-8 h-8 flex items-center justify-center rounded-xl text-khaki-400 hover:text-khaki-600 hover:bg-cream-200/80 transition-all duration-200 cursor-pointer text-sm hover:scale-105 active:scale-95"
          title="收起侧边栏"
        >
          ◂
        </button>
        <span className="font-display font-semibold text-khaki-800 text-sm tracking-wider">{t(lang, 'sidebar_title')}</span>
        <div className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="w-8 h-8 flex items-center justify-center rounded-xl text-khaki-400 hover:text-khaki-600 hover:bg-cream-200/80 transition-all duration-200 cursor-pointer text-sm hover:scale-105 active:scale-95"
          >
            ⋮
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10 animate-fade-in" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-full mt-2 bg-white/95 backdrop-blur-md border border-sand-200/80 rounded-2xl shadow-warm z-20 min-w-[180px] py-2 animate-scale-in">
                <button
                  onClick={() => { onDeleteSessions(); setMenuOpen(false); }}
                  className="w-full text-left px-4 py-2.5 text-sm text-red-500 hover:bg-red-50/80 transition-colors cursor-pointer rounded-lg mx-1"
                  style={{ width: 'calc(100% - 8px)' }}
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
          className="w-full text-left px-4 py-2.5 rounded-xl text-sm text-khaki-700 hover:bg-cream-200/80 hover:text-khaki-800 transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2.5 hover:shadow-soft active:scale-[0.98]"
        >
          <span className="w-6 h-6 rounded-lg bg-gradient-to-br from-cream-400 to-khaki-400 flex items-center justify-center text-white font-bold text-xs shadow-sm">+</span>
          {t(lang, 'new_session')}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4">
        <div className="py-2.5 text-[10px] text-khaki-400 uppercase tracking-[0.15em] font-semibold px-2">
          {t(lang, 'resume_session')}
        </div>
        {sessions.length > 0 ? (
          <div className="space-y-1">
            {sessions.map((s, idx) => (
              <button
                key={s.value}
                onClick={() => onSelectSession(s.value)}
                className="w-full text-left px-4 py-2.5 rounded-xl text-sm text-khaki-600 hover:bg-cream-200/80 hover:text-khaki-800 transition-all duration-200 cursor-pointer truncate animate-slide-up hover:shadow-soft active:scale-[0.98]"
                style={{ animationDelay: `${idx * 50}ms` }}
                title={s.label}
              >
                {s.label}
              </button>
            ))}
          </div>
        ) : (
          <button
            onClick={onListSessions}
            disabled={!connected}
            className="w-full text-left px-4 py-2.5 rounded-xl text-sm text-khaki-400 hover:bg-cream-200/80 hover:text-khaki-600 transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t(lang, 'load_more')}
          </button>
        )}
        {sessions.length > 0 && (
          <button
            onClick={onListSessions}
            disabled={!connected}
            className="w-full text-left px-4 py-2 mt-1.5 rounded-xl text-xs text-khaki-400 hover:bg-cream-200/80 hover:text-khaki-600 transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t(lang, 'load_more')}
          </button>
        )}
      </div>
      <div className="px-5 py-3 border-t border-sand-200/60">
        <div className="flex items-center gap-2.5 text-sm">
          <span className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]' : 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]'}`} />
          <span className="text-khaki-500 font-medium">{connected ? 'Connected' : t(lang, 'disconnected')}</span>
        </div>
      </div>
    </aside>
  );
}
