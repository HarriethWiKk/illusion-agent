import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [rightPanelWidth, setRightPanelWidth] = useState(260);
  const dragRef = useRef<{ side: 'left' | 'right'; startX: number; startW: number } | null>(null);

  const handleResizeStart = useCallback((side: 'left' | 'right', e: React.MouseEvent) => {
    e.preventDefault();
    const startW = side === 'left' ? sidebarWidth : rightPanelWidth;
    dragRef.current = { side, startX: e.clientX, startW };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const maxW = window.innerWidth / 3;
      const dx = ev.clientX - dragRef.current.startX;
      if (dragRef.current.side === 'left') {
        setSidebarWidth(Math.min(maxW, Math.max(280, dragRef.current.startW + dx)));
      } else {
        setRightPanelWidth(Math.min(maxW, Math.max(260, dragRef.current.startW - dx)));
      }
    };
    const onUp = () => { dragRef.current = null; document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [sidebarWidth, rightPanelWidth]);

  // 连接后自动请求 effort、model 和 permissions 列表
  useEffect(() => {
    if (session.connected && session.ready) {
      session.sendRequest({ type: 'select_command', command: 'effort' });
      session.sendRequest({ type: 'select_command', command: 'model' });
      session.sendRequest({ type: 'select_command', command: 'permissions' });
    }
  }, [session.connected, session.ready]);

  const handleSubmit = (line: string) => {
    if (!line.trim()) return;
    const trimmed = line.trim();

    // 特殊命令处理（与 terminal 端对齐）
    if (trimmed === '/new' || trimmed === '/clear' || trimmed === '/clean') {
      session.markSuppressCommandResult();
      session.sendRequest({ type: 'submit_line', line: '/new' });
      setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500);
      return;
    }
    if (trimmed === '/resume') {
      session.sendRequest({ type: 'list_sessions' });
      return;
    }
    if (trimmed === '/model') {
      session.requestSelectCommand('model');
      return;
    }
    if (trimmed === '/effort') {
      session.requestSelectCommand('effort');
      return;
    }
    if (trimmed === '/delete') {
      session.sendRequest({ type: 'select_command', command: 'delete' });
      return;
    }
    if (trimmed.startsWith('/permissions')) {
      session.requestSelectCommand('permissions');
      return;
    }
    // 通用提交
    session.sendRequest({ type: 'submit_line', line: trimmed });
  };
  const handleStop = () => { session.markSuppressCommandResult(); session.sendRequest({ type: 'stop' }); };
  const handleNewSession = () => {
    session.markSuppressCommandResult();
    session.sendRequest({ type: 'submit_line', line: '/new' });
    setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500);
  };
  const handleSelectSession = (id: string) => {
    session.markSuppressCommandResult();
    session.sendRequest({ type: 'apply_select_command', command: 'resume', value: id });
    setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500);
  };
  const handleDeleteSessions = () => { session.markSuppressCommandResult(); session.sendRequest({ type: 'select_command', command: 'delete' }); };
  const handleModeChange = (v: string) => {
    // 与 terminal 端一致：用 submit_line 发送 /permissions set 命令
    session.sendRequest({ type: 'submit_line', line: `/permissions set ${v}` });
  };
  const handleRequestModelList = () => session.sendRequest({ type: 'select_command', command: 'model' });

  const handlePermissionResponse = (requestId: string, allowed: boolean, alwaysAllow: boolean, toolName: string) => {
    session.sendRequest({ type: 'permission_response', request_id: requestId, allowed, always_allow: alwaysAllow, tool_name: toolName });
    session.clearModal();
  };
  const handleQuestionResponse = (requestId: string, answer: string) => {
    session.sendRequest({ type: 'question_response', request_id: requestId, answer });
    session.clearModal();
  };

  const handleConfirmDelete = () => {
    session.markSuppressCommandResult();
    for (const id of deleteSelected) session.sendRequest({ type: 'apply_select_command', command: 'delete', value: id });
    session.clearDeleteSessions(); setDeleteSelected(new Set());
    setTimeout(() => session.sendRequest({ type: 'list_sessions' }), 500);
  };
  const handleCloseDeleteModal = () => { session.clearDeleteSessions(); setDeleteSelected(new Set()); };
  const toggleDeleteItem = (v: string) => setDeleteSelected((prev) => { const n = new Set(prev); n.has(v) ? n.delete(v) : n.add(v); return n; });

  const showDeleteModal = session.deleteSessions.length > 0;
  const regularSessions = session.deleteSessions.filter((s) => s.value !== '__all__');
  const hasAllOption = session.deleteSessions.some((s) => s.value === '__all__');

  const showSelectModal = session.selectModalCommand !== null;
  const selectModalTitle = session.selectModalCommand === 'model' ? t(lang, 'model')
    : session.selectModalCommand === 'permissions' ? t(lang, 'permission')
    : session.selectModalCommand === 'effort' ? t(lang, 'effort')
    : session.selectModalCommand ?? '';

  const handleSelectModalChoose = (value: string) => {
    const cmd = session.selectModalCommand;
    if (!cmd) return;
    session.sendRequest({ type: 'apply_select_command', command: cmd, value });
    session.clearSelectModal();
    if (cmd === 'model') session.sendRequest({ type: 'select_command', command: 'model' });
    if (cmd === 'effort') session.sendRequest({ type: 'select_command', command: 'effort' });
    if (cmd === 'permissions') session.sendRequest({ type: 'select_command', command: 'permissions' });
  };

  return (
    <div className="flex h-screen bg-surface-main select-none">
      <Sidebar lang={lang} connected={session.connected} sessions={session.sessions}
        onNewSession={handleNewSession} onSelectSession={handleSelectSession}
        onListSessions={() => session.sendRequest({ type: 'list_sessions' })}
        onDeleteSessions={handleDeleteSessions}
        collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        width={sidebarWidth} />
      {!sidebarCollapsed && (
        <div className="w-1 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors shrink-0"
          onMouseDown={(e) => handleResizeStart('left', e)} />
      )}
      <div className="flex flex-col flex-1 min-w-0">
        {!session.connected && (
          <div className="px-4 py-2.5 bg-primary-light border-b border-primary/20 text-sm text-primary text-center font-medium">{t(lang, 'connecting')}</div>
        )}
        <ChatArea lang={lang} staticItems={session.staticItems} assistantBuffer={session.assistantBuffer}
          streamingReasoning={session.streamingReasoning} pendingToolCalls={session.pendingToolCalls}
          busy={session.busy} connected={session.connected}
          modal={session.modal} onPermissionResponse={handlePermissionResponse}
          onQuestionResponse={handleQuestionResponse} />
        <PromptInput lang={lang} busy={session.busy} connected={session.connected}
          commands={session.commands} onSubmit={handleSubmit} onStop={handleStop} />
        <Toolbar lang={lang} status={session.status}
          effortOptions={session.effortOptions} modelOptions={session.modelOptions}
          onModeChange={handleModeChange} onModelChange={session.setModelValue}
          onEffortChange={session.setEffortValue} onRequestModelList={handleRequestModelList} />
      </div>
      {!rightPanelCollapsed && (
        <div className="w-1 cursor-col-resize hover:bg-primary/20 active:bg-primary/30 transition-colors shrink-0"
          onMouseDown={(e) => handleResizeStart('right', e)} />
      )}
      <RightPanel lang={lang} status={session.status}
        connected={session.connected} busy={session.busy}
        collapsed={rightPanelCollapsed} onToggle={() => setRightPanelCollapsed(!rightPanelCollapsed)}
        todoItems={session.todoItems} skills={session.skills} plugins={session.plugins}
        rules={session.rules} mcpServers={session.mcpServers}
        width={rightPanelWidth} />

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

      {showSelectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => session.clearSelectModal()} />
          <div className="relative bg-white rounded-2xl shadow-2xl border border-border-light w-[380px] max-h-[60vh] flex flex-col">
            <div className="px-6 py-4 border-b border-border-light">
              <h3 className="text-lg font-semibold text-content-primary">{selectModalTitle}</h3>
            </div>
            <div className="flex-1 overflow-y-auto py-1">
              {session.selectModalOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleSelectModalChoose(opt.value)}
                  className={`w-full text-left px-6 py-3 text-sm transition-colors cursor-pointer flex items-center justify-between ${
                    opt.active ? 'bg-primary-light text-primary font-medium' : 'text-content-secondary hover:bg-surface-hover'
                  }`}
                >
                  <span>{opt.label}</span>
                  {opt.active && (
                    <svg className="w-4 h-4 text-primary shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 8.5l3.5 3.5 6.5-8" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
            <div className="px-6 py-3 border-t border-border-light flex justify-end">
              <button onClick={() => session.clearSelectModal()} className="px-4 py-2 text-sm text-content-secondary hover:bg-surface-hover rounded-lg transition-colors cursor-pointer border border-border-light">{t(lang, 'cancel')}</button>
            </div>
          </div>
        </div>
      )}

      {session.commandResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => session.clearCommandResult()} />
          <div className="relative bg-white rounded-2xl shadow-2xl border border-border-light w-[420px] max-h-[60vh] flex flex-col">
            <div className="px-6 py-4 border-b border-border-light flex items-center justify-between">
              <h3 className="text-sm font-semibold text-content-primary">
                {session.commandResult.type === 'error' ? 'Error' : session.commandResult.type === 'success' ? 'Success' : 'Info'}
              </h3>
              <button onClick={() => session.clearCommandResult()} className="w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary hover:bg-surface-hover transition-colors cursor-pointer">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <pre className="text-sm text-content-primary whitespace-pre-wrap font-mono leading-relaxed">{session.commandResult.text}</pre>
            </div>
            <div className="px-6 py-3 border-t border-border-light flex justify-end">
              <button onClick={() => session.clearCommandResult()} className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors cursor-pointer">OK</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
