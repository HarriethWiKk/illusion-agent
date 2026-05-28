import { useEffect, useMemo, useRef, useState } from 'react';
import { normalizeLanguage, t, type UiLanguage } from './i18n';
import { useWebSocketSession } from './hooks/useWebSocketSession';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import PromptInput from './components/PromptInput';
import Toolbar from './components/Toolbar';
import RightPanel from './components/RightPanel';

const WS_URL = `ws://${window.location.host}/ws`;

export default function App() {
  const session = useWebSocketSession(WS_URL);
  const lang: UiLanguage = useMemo(
    () => normalizeLanguage(session.status?.ui_language),
    [session.status?.ui_language],
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // 乐观更新状态
  const [optimisticMode, setOptimisticMode] = useState<string | null>(null);
  const [optimisticModel, setOptimisticModel] = useState<string | null>(null);
  const [optimisticEffort, setOptimisticEffort] = useState<string | null>(null);
  const prevStatusRef = useRef<Record<string, unknown>>({});

  useEffect(() => {
    const prev = prevStatusRef.current;
    if (prev.permission_mode !== session.status?.permission_mode) setOptimisticMode(null);
    if (prev.model !== session.status?.model) setOptimisticModel(null);
    if (prev.effort !== session.status?.effort) setOptimisticEffort(null);
    prevStatusRef.current = session.status;
  }, [session.status]);

  const mergedStatus = useMemo(() => {
    const s = { ...session.status };
    if (optimisticMode !== null) s.permission_mode = optimisticMode;
    if (optimisticModel !== null) s.model = optimisticModel;
    if (optimisticEffort !== null) s.effort = optimisticEffort;
    return s;
  }, [session.status, optimisticMode, optimisticModel, optimisticEffort]);

  const handleSubmit = (line: string) => {
    if (!line.trim()) return;
    session.sendRequest({ type: 'submit_line', line });
  };

  const handleStop = () => {
    session.sendRequest({ type: 'stop' });
  };

  const handleNewSession = () => {
    session.sendRequest({ type: 'submit_line', line: '/new' });
  };

  const handleSelectSession = (sessionId: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'resume', value: sessionId });
  };

  const handleDeleteSessions = () => {
    session.sendRequest({ type: 'select_command', command: 'delete' });
  };

  const handleConfirmDelete = (sessionId: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'delete', value: sessionId });
    session.clearDeleteSessions();
    setDeleteTarget(null);
  };

  const handleCloseDeleteModal = () => {
    session.clearDeleteSessions();
    setDeleteTarget(null);
  };

  const handleModeChange = (value: string) => {
    setOptimisticMode(value);
    session.sendRequest({ type: 'apply_select_command', command: 'permissions', value });
  };

  const handleModelChange = (value: string) => {
    setOptimisticModel(value);
    session.sendRequest({ type: 'apply_select_command', command: 'model', value });
  };

  const handleEffortChange = (value: string) => {
    setOptimisticEffort(value);
    session.sendRequest({ type: 'apply_select_command', command: 'effort', value });
  };

  const handleRequestModelList = () => {
    session.sendRequest({ type: 'select_command', command: 'model' });
  };

  const showDeleteModal = session.deleteSessions.length > 0;

  return (
    <div className="flex h-screen bg-gradient-to-br from-cream-50 via-sand-50 to-khaki-50">
      <Sidebar
        lang={lang}
        connected={session.connected}
        sessions={session.sessions}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onListSessions={() => session.sendRequest({ type: 'list_sessions' })}
        onDeleteSessions={handleDeleteSessions}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
      <div className="flex flex-col flex-1 min-w-0">
        {!session.connected && (
          <div className="px-4 py-2.5 bg-gradient-to-r from-cream-100 to-sand-100 border-b border-sand-200 text-sm text-khaki-700 text-center font-medium animate-fade-in">
            {t(lang, 'connecting')}
          </div>
        )}
        <ChatArea
          lang={lang}
          staticItems={session.staticItems}
          assistantBuffer={session.assistantBuffer}
          streamingReasoning={session.streamingReasoning}
          pendingToolCalls={session.pendingToolCalls}
          busy={session.busy}
          connected={session.connected}
        />
        <PromptInput
          lang={lang}
          busy={session.busy}
          connected={session.connected}
          commands={session.commands}
          onSubmit={handleSubmit}
          onStop={handleStop}
        />
        <Toolbar
          lang={lang}
          status={mergedStatus}
          selectRequest={session.selectRequest}
          onModeChange={handleModeChange}
          onModelChange={handleModelChange}
          onEffortChange={handleEffortChange}
          onRequestModelList={handleRequestModelList}
        />
      </div>
      <RightPanel
        lang={lang}
        status={mergedStatus}
        connected={session.connected}
        busy={session.busy}
      />

      {/* 删除会话弹窗 */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={handleCloseDeleteModal} />
          <div className="relative bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl border border-sand-200 w-[400px] max-h-[80vh] flex flex-col animate-scale-in">
            <div className="px-6 py-4 border-b border-sand-200/60">
              <h3 className="text-lg font-semibold text-khaki-800">{t(lang, 'confirm_delete')}</h3>
              <p className="text-sm text-khaki-500 mt-1">{t(lang, 'confirm_delete_session')}</p>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {deleteTarget ? (
                <div className="px-6 py-4 text-center">
                  <p className="text-sm text-khaki-600 mb-4">
                    {session.deleteSessions.find(s => s.value === deleteTarget)?.label}
                  </p>
                  <div className="flex gap-3 justify-center">
                    <button
                      onClick={() => setDeleteTarget(null)}
                      className="px-4 py-2 text-sm text-khaki-600 hover:bg-cream-100 rounded-xl transition-colors cursor-pointer"
                    >
                      {t(lang, 'cancel')}
                    </button>
                    <button
                      onClick={() => handleConfirmDelete(deleteTarget)}
                      className="px-4 py-2 text-sm text-white bg-red-500 hover:bg-red-600 rounded-xl transition-colors cursor-pointer"
                    >
                      {t(lang, 'confirm_delete')}
                    </button>
                  </div>
                </div>
              ) : (
                session.deleteSessions.map((s) => (
                  <button
                    key={s.value}
                    onClick={() => {
                      if (s.value === '__all__') {
                        handleConfirmDelete('__all__');
                      } else {
                        setDeleteTarget(s.value);
                      }
                    }}
                    className={`w-full text-left px-6 py-3 text-sm transition-colors cursor-pointer hover:bg-red-50/60 ${
                      s.value === '__all__' ? 'text-red-500 font-medium border-t border-sand-200/60 mt-1 pt-4' : 'text-khaki-700'
                    }`}
                  >
                    {s.label}
                  </button>
                ))
              )}
            </div>
            {!deleteTarget && (
              <div className="px-6 py-3 border-t border-sand-200/60 flex justify-end">
                <button
                  onClick={handleCloseDeleteModal}
                  className="px-4 py-2 text-sm text-khaki-500 hover:text-khaki-700 transition-colors cursor-pointer"
                >
                  {t(lang, 'cancel')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
