import { useEffect, useMemo, useState } from 'react';
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
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [deleteSelected, setDeleteSelected] = useState<Set<string>>(new Set());

  // 连接后自动请求 effort、model 和 permissions 列表
  useEffect(() => {
    if (session.connected && session.ready) {
      session.sendRequest({ type: 'select_command', command: 'effort' });
      session.sendRequest({ type: 'select_command', command: 'model' });
      session.sendRequest({ type: 'select_command', command: 'permissions' });
    }
  }, [session.connected, session.ready]);

  const handleSubmit = (line: string) => { if (!line.trim()) return; session.sendRequest({ type: 'submit_line', line }); };
  const handleStop = () => session.sendRequest({ type: 'stop' });
  const handleNewSession = () => session.sendRequest({ type: 'submit_line', line: '/new' });
  const handleSelectSession = (id: string) => session.sendRequest({ type: 'apply_select_command', command: 'resume', value: id });
  const handleDeleteSessions = () => session.sendRequest({ type: 'select_command', command: 'delete' });
  const handleModeChange = (v: string) => {
    // 与 terminal 端一致：用 submit_line 发送 /permissions set 命令
    session.sendRequest({ type: 'submit_line', line: `/permissions set ${v}` });
  };
  const handleRequestModelList = () => session.sendRequest({ type: 'select_command', command: 'model' });

  const handleConfirmDelete = () => {
    for (const id of deleteSelected) session.sendRequest({ type: 'apply_select_command', command: 'delete', value: id });
    session.clearDeleteSessions(); setDeleteSelected(new Set());
    setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500);
  };
  const handleCloseDeleteModal = () => { session.clearDeleteSessions(); setDeleteSelected(new Set()); };
  const toggleDeleteItem = (v: string) => setDeleteSelected((prev) => { const n = new Set(prev); n.has(v) ? n.delete(v) : n.add(v); return n; });

  const showDeleteModal = session.deleteSessions.length > 0;
  const regularSessions = session.deleteSessions.filter((s) => s.value !== '__all__');
  const hasAllOption = session.deleteSessions.some((s) => s.value === '__all__');

  return (
    <div className="flex h-screen bg-surface-main">
      <Sidebar lang={lang} connected={session.connected} sessions={session.sessions}
        onNewSession={handleNewSession} onSelectSession={handleSelectSession}
        onListSessions={() => session.sendRequest({ type: 'list_sessions' })}
        onDeleteSessions={handleDeleteSessions}
        collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
      <div className="flex flex-col flex-1 min-w-0">
        {!session.connected && (
          <div className="px-4 py-2.5 bg-primary-light border-b border-primary/20 text-sm text-primary text-center font-medium">{t(lang, 'connecting')}</div>
        )}
        <ChatArea lang={lang} staticItems={session.staticItems} assistantBuffer={session.assistantBuffer}
          streamingReasoning={session.streamingReasoning} pendingToolCalls={session.pendingToolCalls}
          busy={session.busy} connected={session.connected} />
        <PromptInput lang={lang} busy={session.busy} connected={session.connected}
          commands={session.commands} onSubmit={handleSubmit} onStop={handleStop} />
        <Toolbar lang={lang} status={session.status}
          effortOptions={session.effortOptions} modelOptions={session.modelOptions}
          onModeChange={handleModeChange} onModelChange={session.setModelValue}
          onEffortChange={session.setEffortValue} onRequestModelList={handleRequestModelList} />
      </div>
      <RightPanel lang={lang} status={session.status}
        connected={session.connected} busy={session.busy}
        collapsed={rightPanelCollapsed} onToggle={() => setRightPanelCollapsed(!rightPanelCollapsed)} />

      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={handleCloseDeleteModal} />
          <div className="relative bg-white rounded-2xl shadow-2xl border border-border-light w-[420px] max-h-[70vh] flex flex-col">
            <div className="px-6 py-4 border-b border-border-light">
              <h3 className="text-lg font-semibold text-content-primary">{t(lang, 'delete_session')}</h3>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {regularSessions.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-content-disabled">{t(lang, 'no_sessions')}</div>
              ) : regularSessions.map((s) => (
                <label key={s.value} className="flex items-center gap-3 px-6 py-3 cursor-pointer hover:bg-surface-hover transition-colors">
                  <input type="checkbox" checked={deleteSelected.has(s.value)} onChange={() => toggleDeleteItem(s.value)} className="w-4 h-4 rounded accent-danger" />
                  <span className="text-sm text-content-secondary truncate flex-1">{s.label}</span>
                </label>
              ))}
            </div>
            <div className="px-6 py-4 border-t border-border-light flex items-center justify-between">
              <div>{hasAllOption && (
                <button onClick={() => { session.sendRequest({ type: 'apply_select_command', command: 'delete', value: '__all__' }); session.clearDeleteSessions(); setDeleteSelected(new Set()); setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500); }}
                  className="px-4 py-2 text-sm text-danger hover:bg-red-50 rounded-lg transition-colors cursor-pointer">{t(lang, 'delete_all')}</button>
              )}</div>
              <div className="flex gap-2">
                <button onClick={handleCloseDeleteModal} className="px-4 py-2 text-sm text-content-secondary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer border border-border-light">{t(lang, 'cancel')}</button>
                <button onClick={handleConfirmDelete} disabled={deleteSelected.size === 0}
                  className="px-4 py-2 text-sm text-white bg-danger hover:bg-danger-hover rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                  {t(lang, 'confirm_delete')} ({deleteSelected.size})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
