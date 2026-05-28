import { t, type UiLanguage } from '../i18n';

interface SidebarProps {
  lang: UiLanguage;
  connected: boolean;
  onNewSession: () => void;
  onSelectSession: (sessionId: string) => void;
  onListSessions: () => void;
}

export default function Sidebar({ lang, connected, onNewSession, onListSessions }: SidebarProps) {
  return (
    <aside className="w-[280px] bg-gray-50 border-r border-gray-200 flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <button className="text-gray-400 hover:text-gray-600 text-sm cursor-pointer">←</button>
        <span className="font-semibold text-gray-900 text-sm">{t(lang, 'sidebar_title')}</span>
        <button className="text-gray-400 hover:text-gray-600 text-sm cursor-pointer">⋮</button>
      </div>
      <div className="px-3 py-2">
        <button
          onClick={onNewSession}
          disabled={!connected}
          className="w-full text-left px-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-200 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
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
          disabled={!connected}
          className="w-full text-left px-3 py-2 rounded-md text-sm text-gray-500 hover:bg-gray-200 hover:text-gray-700 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {t(lang, 'load_more')}
        </button>
      </div>
      {/* 连接状态指示器 */}
      <div className="px-4 py-2 border-t border-gray-200">
        <div className="flex items-center gap-2 text-xs">
          <span className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-gray-500">{connected ? 'Connected' : t(lang, 'disconnected')}</span>
        </div>
      </div>
      <div className="flex items-center justify-around px-4 py-3 border-t border-gray-200">
        <button className="text-gray-400 hover:text-gray-600 cursor-pointer" title={t(lang, 'settings')}>⚙</button>
        <button className="text-gray-400 hover:text-gray-600 cursor-pointer" title={t(lang, 'help')}>?</button>
      </div>
    </aside>
  );
}
