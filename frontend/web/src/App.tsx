import { useMemo } from 'react';
import { normalizeLanguage, t, type UiLanguage } from './i18n';
import { useWebSocketSession } from './hooks/useWebSocketSession';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import PromptInput from './components/PromptInput';
import Toolbar from './components/Toolbar';

const WS_URL = `ws://${window.location.host}/ws`;

export default function App() {
  const session = useWebSocketSession(WS_URL);
  const lang: UiLanguage = useMemo(
    () => normalizeLanguage(session.status?.ui_language),
    [session.status?.ui_language],
  );

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

  const handleModeChange = (value: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'permissions', value });
  };

  const handleModelChange = (value: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'model', value });
  };

  const handleEffortChange = (value: string) => {
    session.sendRequest({ type: 'apply_select_command', command: 'effort', value });
  };

  // 请求模型列表（用于工具栏模型下拉）
  const handleRequestModelList = () => {
    session.sendRequest({ type: 'select_command', command: 'model' });
  };

  return (
    <div className="flex h-screen bg-white">
      <Sidebar
        lang={lang}
        connected={session.connected}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onListSessions={() => session.sendRequest({ type: 'list_sessions' })}
      />
      <div className="flex flex-col flex-1 min-w-0">
        {!session.connected && (
          <div className="px-4 py-2 bg-yellow-50 border-b border-yellow-200 text-xs text-yellow-700 text-center">
            {t(lang, 'connecting')}
          </div>
        )}
        <ChatArea
          lang={lang}
          staticItems={session.staticItems}
          assistantBuffer={session.assistantBuffer}
          pendingToolCalls={session.pendingToolCalls}
          busy={session.busy}
          ready={session.ready}
          connected={session.connected}
        />
        <PromptInput
          lang={lang}
          busy={session.busy}
          connected={session.connected}
          onSubmit={handleSubmit}
          onStop={handleStop}
        />
        <Toolbar
          lang={lang}
          status={session.status}
          selectRequest={session.selectRequest}
          onModeChange={handleModeChange}
          onModelChange={handleModelChange}
          onEffortChange={handleEffortChange}
          onRequestModelList={handleRequestModelList}
        />
      </div>
    </div>
  );
}
