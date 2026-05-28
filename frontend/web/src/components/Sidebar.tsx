import React from 'react';
import { t, type UiLanguage } from '../i18n';

interface SidebarProps {
  lang: UiLanguage;
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onListSessions: () => void;
}

export default function Sidebar({ lang, onNewSession, onSelectSession, onListSessions }: SidebarProps) {
  return (
    <aside className="w-[280px] bg-gray-50 border-r border-gray-200 flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <button className="text-gray-400 hover:text-gray-600 text-sm">←</button>
        <span className="font-semibold text-gray-900 text-sm">{t(lang, 'sidebar_title')}</span>
        <button className="text-gray-400 hover:text-gray-600 text-sm">⋮</button>
      </div>
      <div className="px-3 py-2">
        <button
          onClick={onNewSession}
          className="w-full text-left px-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-200 transition-colors"
        >
          + {t(lang, 'new_session')}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3">
        <div className="py-2 text-xs text-gray-400 uppercase tracking-wider">
          {t(lang, 'resume_session')}
        </div>
        <button
          onClick={onListSessions}
          className="w-full text-left px-3 py-2 rounded-md text-sm text-gray-500 hover:bg-gray-200 hover:text-gray-700 transition-colors"
        >
          {t(lang, 'load_more')}
        </button>
      </div>
      <div className="flex items-center justify-around px-4 py-3 border-t border-gray-200">
        <button className="text-gray-400 hover:text-gray-600" title={t(lang, 'settings')}>⚙</button>
        <button className="text-gray-400 hover:text-gray-600" title={t(lang, 'help')}>?</button>
      </div>
    </aside>
  );
}
