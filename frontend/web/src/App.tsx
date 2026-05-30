import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { normalizeLanguage, t, type UiLanguage } from './i18n';
import { useWebSocketSession, type SelectRequestPayload } from './hooks/useWebSocketSession';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import PromptInput from './components/PromptInput';
import Toolbar from './components/Toolbar';
import RightPanel from './components/RightPanel';

const WS_URL = `ws://${window.location.host}/ws`;
const TOAST_DURATION = 5000;

export default function App() {
  const session = useWebSocketSession(WS_URL);
  const lang: UiLanguage = useMemo(
    () => normalizeLanguage(session.status?.ui_language),
    [session.status?.ui_language],
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [rightPanelWidth, setRightPanelWidth] = useState(260);
  const dragRef = useRef<{ side: 'left' | 'right'; startX: number; startW: number } | null>(null);

  // 内联选项状态
  const [inlineOptions, setInlineOptions] = useState<SelectRequestPayload | null>(null);

  // Toast 状态
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastHoverRef = useRef(false);

  const showToast = useCallback((text: string, type: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastMessage({ text, type: type as 'success' | 'error' | 'info' });
    toastHoverRef.current = false;
    toastTimerRef.current = setTimeout(() => {
      if (!toastHoverRef.current) { setToastMessage(null); }
      toastTimerRef.current = null;
    }, TOAST_DURATION);
  }, []);

  const handleToastMouseEnter = useCallback(() => {
    toastHoverRef.current = true;
    if (toastTimerRef.current) { clearTimeout(toastTimerRef.current); toastTimerRef.current = null; }
  }, []);

  const handleToastMouseLeave = useCallback(() => {
    toastHoverRef.current = false;
    toastTimerRef.current = setTimeout(() => { setToastMessage(null); toastTimerRef.current = null; }, TOAST_DURATION);
  }, []);

  // 注册回调
  useEffect(() => {
    session.setOnSelectRequest((payload) => setInlineOptions(payload));
    session.setOnCommandResult((text, type) => showToast(text, type));
    return () => { session.setOnSelectRequest(null); session.setOnCommandResult(null); };
  }, [session.setOnSelectRequest, session.setOnCommandResult, showToast]);

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

  const handleSubmit = (line: string) => {
    if (!line.trim()) return;
    const trimmed = line.trim();

    // /language → 前端本地构建选项
    if (trimmed === '/language' || trimmed === '/language show') {
      const current = normalizeLanguage(session.status?.ui_language);
      setInlineOptions({
        command: 'language',
        title: t(lang, 'language'),
        options: [
          { value: 'set zh-CN', label: '简体中文', description: '中文界面', active: current === 'zh-CN' },
          { value: 'set en', label: 'English', description: 'English UI', active: current === 'en' },
        ],
      });
      return;
    }

    // /resume → 发送 list_sessions（和 terminal 端一致）
    if (trimmed === '/resume') {
      session.sendRequest({ type: 'list_sessions' });
      return;
    }

    // 通过 select_command 获取内联选项的命令
    const selectCommands = ['context', 'rewind', 'model', 'delete'];
    const cmdName = trimmed.startsWith('/') ? (trimmed.slice(1).split(/\s+/)[0] ?? '') : '';
    if (cmdName && selectCommands.includes(cmdName)) {
      session.setBusyTrue();
      session.requestSelectCommand(cmdName);
      return;
    }

    // 其他所有命令（含 /effort）→ 直接提交，结果走 toast
    session.setBusyTrue();
    session.sendRequest({ type: 'submit_line', line: trimmed });
  };

  const handleInlineSelect = useCallback((command: string, value: string) => {
    setInlineOptions(null);
    session.sendRequest({ type: 'apply_select_command', command, value });
  }, [session.sendRequest]);

  const handleInlineClose = useCallback(() => setInlineOptions(null), []);

  const handleStop = () => { session.sendRequest({ type: 'stop' }); };
  const handleNewSession = () => {
    session.sendRequest({ type: 'submit_line', line: '/new' });
  };
  const handleSelectSession = (id: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'resume', value: id });
  };
  const handleDeleteSessions = useCallback(() => {
    session.requestSelectCommand('delete');
  }, [session.requestSelectCommand]);

  const handlePermissionResponse = (requestId: string, allowed: boolean, alwaysAllow: boolean, toolName: string) => {
    session.sendRequest({ type: 'permission_response', request_id: requestId, allowed, always_allow: alwaysAllow, tool_name: toolName });
    session.clearModal();
  };
  const handleQuestionResponse = (requestId: string, answer: string) => {
    session.sendRequest({ type: 'question_response', request_id: requestId, answer });
    session.clearModal();
  };

  return (
    <div className="flex h-screen bg-surface-main">
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
          commands={session.commands} onSubmit={handleSubmit} onStop={handleStop}
          inlineOptions={inlineOptions} onInlineSelect={handleInlineSelect} onInlineClose={handleInlineClose} />
        <Toolbar lang={lang} status={session.status}
          effortOptions={session.effortOptions} modelOptions={session.modelOptions}
          onModeChange={(v) => session.sendRequest({ type: 'submit_line', line: `/permissions set ${v}` })}
          onModelChange={session.setModelValue}
          onEffortChange={session.setEffortValue}
          onRequestModelList={() => session.requestSelectCommand('model')} />
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

      {/* Toast 通知 */}
      {toastMessage && (
        <div className="fixed bottom-20 right-6 z-50 animate-fade-in"
          onMouseEnter={handleToastMouseEnter} onMouseLeave={handleToastMouseLeave}>
          <div className="bg-white rounded-xl shadow-lg px-4 py-3 max-w-sm">
            <div className="flex items-start gap-3">
              <pre className="text-sm text-content-primary whitespace-pre-wrap font-mono leading-relaxed flex-1 max-h-40 overflow-y-auto">{toastMessage.text}</pre>
              <button onClick={() => setToastMessage(null)}
                className="shrink-0 w-5 h-5 flex items-center justify-center rounded text-content-disabled hover:text-content-primary hover:bg-surface-hover transition-colors cursor-pointer">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
