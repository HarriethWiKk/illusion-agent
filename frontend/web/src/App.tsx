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

  // 乐观更新状态：用户在 Toolbar 切换后立即生效，后端 state_snapshot 到达后自动清除
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

  // 合并后端状态与乐观覆盖，Toolbar 和 RightPanel 共用同一份
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

  const handleCommand = (line: string) => {
    session.sendRequest({ type: 'submit_line', line });
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

  return (
    <div className="flex h-screen bg-gradient-to-br from-cream-50 via-sand-50 to-khaki-50">
      <Sidebar
        lang={lang}
        connected={session.connected}
        sessions={session.sessions}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onListSessions={() => session.sendRequest({ type: 'list_sessions' })}
        onCommand={handleCommand}
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
    </div>
  );
}
