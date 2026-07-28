/**
 * @fileoverview Web 前端应用主组件
 *
 * 本模块是 IllusionAgent Web 前端的核心入口，负责：
 * 1. 整体应用布局与组件组合
 * 2. WebSocket 会话管理
 * 3. 处理用户提交的命令
 * 4. 管理侧边栏和右侧面板的折叠/展开状态
 * 5. Toast 通知显示
 * 6. 删除会话弹窗
 * 7. 权限和问答模态框响应
 *
 * @module App
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { normalizeLanguage, t, type UiLanguage } from './i18n';
import { useWebSocketSession, type SelectRequestPayload } from './hooks/useWebSocketSession';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import PromptInput from './components/PromptInput';
import Toolbar from './components/Toolbar';
import RightPanel from './components/RightPanel';
import { CustomInputModal } from './components/CustomInputModal';

/** WebSocket 连接地址 */
const WS_URL = `ws://${window.location.host}/ws`;

/** Toast 通知显示时长（毫秒） */
const TOAST_DURATION = 5000;

/** B 通道允许的指令集合（前端识别并走 web_query） */
const B_COMMANDS = ['rewind', 'compact', 'context', 'export', 'init', 'passes', 'turns', 'output-style', 'language', 'max-tokens'];

/**
 * 应用主组件
 *
 * Web 前端的根组件，负责组合所有子组件并管理全局状态。
 *
 * @returns 返回应用的 JSX 元素
 */
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

  // 自定义数字输入模态框状态（/max-tokens 与 /context-window 的 custom 分支触发）
  const [customInputModal, setCustomInputModal] = useState<{
    prompt: string;
    command: 'max-tokens' | 'context-window';
    invalidMessage?: string;
  } | null>(null);

  // 回退确认弹窗状态
  const [rewindConfirm, setRewindConfirm] = useState<{ turns: number } | null>(null);
  // 重新生成：存储待重发的 user 消息文本，rewind 完成后自动重发
  const pendingRegenerateRef = useRef<string | null>(null);
  const prevBusyRef = useRef(false);

  // Toast 状态
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastHoverRef = useRef(false);
  const toastKeyRef = useRef(0);

  const closeToast = useCallback(() => {
    setToastExiting(true);
    setTimeout(() => { setToastMessage(null); setToastExiting(false); }, 200);
  }, []);

  const showToast = useCallback((text: string, type: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastKeyRef.current += 1;
    setToastExiting(false);
    setToastMessage({ text, type: type as 'success' | 'error' | 'info' });
    toastHoverRef.current = false;
    toastTimerRef.current = setTimeout(() => {
      if (!toastHoverRef.current) { closeToast(); }
      toastTimerRef.current = null;
    }, TOAST_DURATION);
  }, [closeToast]);

  const handleToastMouseEnter = useCallback(() => {
    toastHoverRef.current = true;
    if (toastTimerRef.current) { clearTimeout(toastTimerRef.current); toastTimerRef.current = null; }
  }, []);

  const handleToastMouseLeave = useCallback(() => {
    toastHoverRef.current = false;
    toastTimerRef.current = setTimeout(() => { closeToast(); toastTimerRef.current = null; }, TOAST_DURATION);
  }, [closeToast]);

  /**
   * 注册回调函数
   *
   * 将内联选项请求和指令结果回调注册到会话中。
   */
  useEffect(() => {
    session.setOnSelectRequest((payload) => setInlineOptions(payload));
    session.setOnCommandResult((text, type) => showToast(text, type));
    return () => { session.setOnSelectRequest(null); session.setOnCommandResult(null); };
  }, [session.setOnSelectRequest, session.setOnCommandResult, showToast]);

  /**
   * 处理面板大小调整开始
   *
   * 当用户开始拖拽面板边缘时触发，用于调整侧边栏或右侧面板的宽度。
   *
   * @param side - 要调整的面板（'left' 或 'right'）
   * @param e - 鼠标事件
   */
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

  /**
   * 处理用户提交的命令（三通道有序判定）
   *
   * 通道隔离原则：
   * - B 通道（web_query）：输入框识别的精细化指令（rewind/compact/context/export/init/
   *   passes/turns/output-style/language/max-tokens），走 web_query 结构化处理。
   * - 文本通道（submit_line）：普通文本，或未被识别的斜杠指令（A 类如 /resume /model
   *   以及已删除指令），全部当普通文本发给 LLM。
   *
   * A 类指令（new/resume/delete/model/effort/permissions/plan）已完全交由 UI 控件承载，
   * 输入框不识别，落入文本通道。
   *
   * @param line - 用户输入的命令
   */
  const handleSubmit = (line: string) => {
    if (!line.trim()) return;
    const trimmed = line.trim();

    // 通道 1：B 类斜杠指令 → web_query（精细化处理，不经过命令注册表）
    if (trimmed.startsWith('/')) {
      const cmdName = trimmed.slice(1).split(/\s+/)[0] ?? '';
      const args = trimmed.slice(1 + cmdName.length).trim();

      // /language（无参数）→ 弹出语言选择框，不走 web_query
      if (cmdName === 'language' && !args) {
        const current = String(session.status?.ui_language ?? 'zh-CN');
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
      if (B_COMMANDS.includes(cmdName)) {
        session.setBusyTrue();
        session.sendRequest({
          type: 'web_query',
          command: cmdName,
          args,
          request_id: `q-${Date.now()}`,
        });
        return;
      }
    }

    // 通道 2：所有其他输入（含 /resume、/model 等非 B 类指令）→ 当 user 消息发给 LLM
    // treat_as_text=true 告诉后端跳过命令注册表，直接当文本提交给 LLM
    session.setBusyTrue();
    session.sendRequest({ type: 'submit_line', line: trimmed, treat_as_text: true });
  };

  /**
   * 处理内联选项选择
   *
   * 当用户从内联选项列表中选择一个选项时触发。
   *
   * @param command - 命令名称
   * @param value - 选中的值
   */
  const handleInlineSelect = useCallback((command: string, value: string) => {
    // max-tokens custom 分支：切换到数字输入模态框
    if (command === 'max-tokens' && value === 'custom') {
      setCustomInputModal({
        prompt: t(lang, 'maxTokensCustomPrompt'),
        command: 'max-tokens',
        invalidMessage: t(lang, 'maxTokensInvalid'),
      });
      setInlineOptions(null);
      return;
    }
    // context-window __custom__ 分支：切换到数字输入模态框
    if (command === 'context-window' && value === '__custom__') {
      setCustomInputModal({
        prompt: t(lang, 'contextWindowCustomPrompt'),
        command: 'context-window',
        invalidMessage: t(lang, 'contextWindowInvalid'),
      });
      setInlineOptions(null);
      return;
    }
    setInlineOptions(null);
    // language 走 web_query 通道（前端弹出选择框后提交）
    if (command === 'language') {
      session.sendRequest({
        type: 'web_query',
        command,
        args: value,
        request_id: `q-${Date.now()}`,
      });
    } else {
      // rewind/context 等多步指令仍走 apply_select_command
      session.sendRequest({ type: 'apply_select_command', command, value });
    }
  }, [session.sendRequest, lang]);

  /**
   * 处理内联选项关闭
   *
   * 当用户关闭内联选项列表时触发。
   */
  const handleInlineClose = useCallback(() => setInlineOptions(null), []);

  /**
   * 处理自定义数字输入提交
   *
   * 由 CustomInputModal 触发，将用户输入的数字字符串通过 apply_select_command
   * 通道发回后端（与 rewind/context 等多步指令一致）。
   *
   * @param value - 用户输入的数字字符串
   */
  const handleCustomSubmit = useCallback((value: string) => {
    if (customInputModal) {
      session.sendRequest({
        type: 'apply_select_command',
        command: customInputModal.command,
        value,
      });
    }
    setCustomInputModal(null);
  }, [customInputModal, session.sendRequest]);

  /**
   * 处理自定义数字输入取消
   *
   * 关闭自定义输入模态框，不做任何提交。
   */
  const handleCustomCancel = useCallback(() => {
    setCustomInputModal(null);
  }, []);

  // 删除会话弹窗状态（本地控制，数据源来自 session.sessions 主列表）
  const [deleteSelected, setDeleteSelected] = useState<Set<string>>(new Set());
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);

  /** 处理停止当前任务 */
  const handleStop = () => { session.sendRequest({ type: 'stop' }); };

  /**
   * 处理回退到指定轮次
   *
   * 由 ChatArea 中 user 消息的撤销按钮触发，弹出模式选择弹窗。
   *
   * @param turnsToRewind - 需要回退的轮次数
   */
  const handleRewindToTurn = useCallback((turnsToRewind: number) => {
    setRewindConfirm({ turns: turnsToRewind });
  }, []);

  /**
   * 确认回退 —— 根据用户选择的模式执行 /rewind N mode
   *
   * 通过 submit_line 通道（treat_as_text 缺省=false）直接走命令注册表，
   * 绕过 web_query 的多步弹窗流程。
   *
   * @param mode - 回退模式：code / conversation / both
   */
  const handleConfirmRewind = useCallback((mode: string) => {
    const turns = rewindConfirm?.turns ?? 1;
    setRewindConfirm(null);
    session.setBusyTrue();
    session.sendRequest({ type: 'submit_line', line: `/rewind ${turns} ${mode}` });
  }, [rewindConfirm, session]);

  /**
   * 处理重新生成
   *
   * 找到最后一条 user 消息文本，先 /rewind 1 both 回退一轮，
   * rewind 完成后（busy→false）自动重发 user 消息。
   */
  const handleRegenerate = useCallback(() => {
    const lastUserMsg = [...session.staticItems].reverse().find((i) => i.role === 'user' && !i.text.startsWith('/'));
    if (!lastUserMsg) return;
    pendingRegenerateRef.current = lastUserMsg.text;
    session.setBusyTrue();
    session.sendRequest({ type: 'submit_line', line: '/rewind 1 both' });
  }, [session]);

  // 监听 busy 状态变化：rewind 完成后自动重发 user 消息（重新生成）
  useEffect(() => {
    if (prevBusyRef.current && !session.busy && pendingRegenerateRef.current) {
      const text = pendingRegenerateRef.current;
      pendingRegenerateRef.current = null;
      session.setBusyTrue();
      session.sendRequest({ type: 'submit_line', line: text, treat_as_text: true });
    }
    prevBusyRef.current = session.busy;
  }, [session.busy, session]);

  /** 处理新建会话 */
  const handleNewSession = () => {
    session.sendRequest({ type: 'web_new_session' });
  };

  /**
   * 处理选择会话（A 通道，零 suppress）
   *
   * 点击会话项 → 发送 web_restore_session，前端立即进入 restoring 态显示加载动画，
   * 收到 web_restore_completed 后清除动画并替换转录。不再有 /resume 弹框副作用。
   *
   * @param id - 会话 ID
   */
  const handleSelectSession = useCallback((id: string) => {
    session.setRestoringSessionId(id);
    session.sendRequest({ type: 'web_restore_session', session_id: id });
  }, [session.setRestoringSessionId, session.sendRequest]);

  /** 处理列出会话（A 通道，后端推送 web_sessions） */
  const handleListSessions = useCallback(() => {
    session.sendRequest({ type: 'web_request_sessions' });
  }, [session.sendRequest]);

  /** 处理删除会话：打开删除弹窗（数据源来自 session.sessions 主列表） */
  const handleDeleteSessions = useCallback(() => {
    setDeleteSelected(new Set());
    setDeleteModalOpen(true);
  }, []);
  /**
   * 处理确认删除
   *
   * 删除所有选中的会话。
   */
  const handleConfirmDelete = useCallback(() => {
    const ids = Array.from(deleteSelected);
    if (ids.length > 0) {
      // 直接发送删除请求；若包含当前会话，后端会原子化地新建空会话，
      // 避免前端"先删后建"两阶段逻辑的竞态。
      session.deleteSessions(ids);
    }
    setDeleteModalOpen(false);
    setDeleteSelected(new Set());
  }, [deleteSelected, session.deleteSessions]);

  /**
   * 处理关闭删除模态框
   *
   * 关闭删除会话弹窗并清除选中状态。
   */
  const handleCloseDeleteModal = useCallback(() => {
    setDeleteModalOpen(false);
    setDeleteSelected(new Set());
  }, []);

  /**
   * 切换删除项选中状态
   *
   * @param v - 会话 ID
   */
  const toggleDeleteItem = useCallback((v: string) => {
    setDeleteSelected((prev) => { const n = new Set(prev); n.has(v) ? n.delete(v) : n.add(v); return n; });
  }, []);

  /** 是否显示删除模态框（本地控制，不再依赖 select_request:delete 填充） */
  const showDeleteModal = deleteModalOpen;
  /** 待删除的普通会话列表（来自主会话列表 session.sessions） */
  const regularSessions = session.sessions;
  /** 总是提供"删除全部"入口 */
  const hasAllOption = session.sessions.length > 0;

  /**
   * 处理权限响应
   *
   * @param requestId - 请求 ID
   * @param allowed - 是否允许
   * @param alwaysAllow - 是否总是允许
   * @param toolName - 工具名称
   */
  const handlePermissionResponse = (requestId: string, allowed: boolean, alwaysAllow: boolean, toolName: string) => {
    session.sendRequest({ type: 'permission_response', request_id: requestId, allowed, always_allow: alwaysAllow, tool_name: toolName });
    session.clearModal();
  };

  /**
   * 处理问答响应
   *
   * @param requestId - 请求 ID
   * @param answer - 用户回答
   */
  const handleQuestionResponse = (requestId: string, answer: string) => {
    session.sendRequest({ type: 'question_response', request_id: requestId, answer });
    session.clearModal();
  };

  return (
    <div className="flex h-screen">
      <Sidebar lang={lang} connected={session.connected} sessions={session.sessions}
        onNewSession={handleNewSession} onSelectSession={handleSelectSession}
        onListSessions={handleListSessions}
        onDeleteSessions={handleDeleteSessions}
        collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        width={sidebarWidth} restoringSessionId={session.restoringSessionId} />
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
          onQuestionResponse={handleQuestionResponse} restoringSessionId={session.restoringSessionId}
          onRewindToTurn={handleRewindToTurn} onRegenerate={handleRegenerate} />
        <PromptInput lang={lang} busy={session.busy} connected={session.connected}
          commands={session.commands} onSubmit={handleSubmit} onStop={handleStop}
          inlineOptions={inlineOptions} onInlineSelect={handleInlineSelect} onInlineClose={handleInlineClose} />
        <Toolbar lang={lang} status={session.status}
          modelOptions={session.modelOptions}
          onSetSetting={(key, value) => {
            if (key === 'model') session.setModelSwitching(true);
            session.sendRequest({ type: 'web_set_setting', setting_key: key, setting_value: value });
          }}
          onRequestModels={() => session.sendRequest({ type: 'web_request_models' })}
          modelSwitching={session.modelSwitching} />
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

      {/* 删除会话弹窗（仅 sidebar 触发） */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/35 backdrop-blur-md animate-fade-in" onClick={handleCloseDeleteModal} />
          <div className="relative glass-overlay rounded-2xl w-[420px] max-h-[70vh] flex flex-col animate-scale-in modal-origin-center">
            <div className="px-6 py-4 border-b border-border-light">
              <h3 className="text-lg font-semibold text-content-primary">{t(lang, 'delete_session')}</h3>
            </div>
            <div className="flex-1 overflow-y-auto py-2">
              {regularSessions.length === 0 ? (
                <div className="px-6 py-8 text-center text-sm text-content-disabled">{t(lang, 'no_sessions')}</div>
              ) : regularSessions.map((s) => (
                <label key={s.value} className="flex items-center gap-3 px-6 py-3 cursor-pointer glass-option-hover transition-colors rounded-lg mx-1">
                  <input type="checkbox" checked={deleteSelected.has(s.value)} onChange={() => toggleDeleteItem(s.value)} className="w-4 h-4 rounded accent-danger" />
                  <span className="text-sm text-content-secondary truncate flex-1">{s.label}</span>
                </label>
              ))}
            </div>
            <div className="px-6 py-4 border-t border-border-light flex items-center justify-between">
              <div>{hasAllOption && (
                <button onClick={() => {
                  // 直接删除全部；后端会原子化地新建空会话，避免两阶段竞态
                  session.deleteSessions([], true);
                  setDeleteModalOpen(false); setDeleteSelected(new Set());
                }} className="danger-action px-4 py-2 text-sm text-danger rounded-lg cursor-pointer">{t(lang, 'delete_all')}</button>
              )}</div>
              <div className="flex gap-2">
                <button onClick={handleCloseDeleteModal} className="px-4 py-2 text-sm text-content-secondary glass-option-hover rounded-lg transition-colors cursor-pointer border border-white/40">{t(lang, 'cancel')}</button>
                <button onClick={handleConfirmDelete} disabled={deleteSelected.size === 0}
                  className="px-4 py-2 text-sm text-white bg-danger hover:bg-danger-hover rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
                  {t(lang, 'confirm_delete')} ({deleteSelected.size})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 回退确认弹窗（选择回退范围） */}
      {rewindConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/35 backdrop-blur-md animate-fade-in" onClick={() => setRewindConfirm(null)} />
          <div className="relative glass-overlay rounded-2xl w-[380px] flex flex-col animate-scale-in modal-origin-center">
            <div className="px-6 py-4 border-b border-border-light">
              <h3 className="text-lg font-semibold text-content-primary">{t(lang, 'rewind_confirm_title')}</h3>
            </div>
            <div className="py-2 px-1">
              {([
                { mode: 'both', label: t(lang, 'rewind_both'), desc: t(lang, 'rewind_both_desc') },
                { mode: 'conversation', label: t(lang, 'rewind_conversation'), desc: t(lang, 'rewind_conversation_desc') },
                { mode: 'code', label: t(lang, 'rewind_code'), desc: t(lang, 'rewind_code_desc') },
              ] as const).map((opt) => (
                <button
                  key={opt.mode}
                  onClick={() => handleConfirmRewind(opt.mode)}
                  className="w-full text-left px-6 py-3 cursor-pointer glass-option-hover transition-colors rounded-lg flex items-center justify-between group"
                >
                  <div>
                    <div className="text-sm font-medium text-content-primary">{opt.label}</div>
                    <div className="text-xs text-content-disabled mt-0.5">{opt.desc}</div>
                  </div>
                  <svg className="w-4 h-4 text-content-disabled opacity-0 group-hover:opacity-100 transition-opacity" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M6 3l5 5-5 5" />
                  </svg>
                </button>
              ))}
            </div>
            <div className="px-6 py-4 border-t border-border-light flex justify-end">
              <button onClick={() => setRewindConfirm(null)} className="px-4 py-2 text-sm text-content-secondary glass-option-hover rounded-lg transition-colors cursor-pointer border border-white/40">
                {t(lang, 'cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 自定义数字输入模态框（/max-tokens custom 与 /context-window __custom__ 分支） */}
      {customInputModal && (
        <CustomInputModal
          lang={lang}
          prompt={customInputModal.prompt}
          invalidMessage={customInputModal.invalidMessage}
          onSubmit={handleCustomSubmit}
          onCancel={handleCustomCancel}
        />
      )}

      {/* Toast 通知 */}
      {toastMessage && (
        <div
          key={toastKeyRef.current}
          className={`fixed bottom-20 right-6 z-50 ${toastExiting ? 'animate-toast-out' : 'animate-toast-in'}`}
          onMouseEnter={handleToastMouseEnter} onMouseLeave={handleToastMouseLeave}
        >
          <div className="glass-surface border border-black/10 rounded-2xl max-w-sm overflow-hidden">
            <div className="flex items-start gap-3 px-4 py-3">
              <pre className="text-sm text-content-primary whitespace-pre-wrap font-mono leading-relaxed flex-1 max-h-40 overflow-y-auto">{toastMessage.text}</pre>
              <button onClick={closeToast}
                className="shrink-0 w-5 h-5 flex items-center justify-center rounded text-content-disabled hover:text-content-primary glass-option-hover transition-colors cursor-pointer">
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
              </button>
            </div>
            <div className="h-0.5 bg-black/10">
              <div
                key={toastKeyRef.current}
                className={`h-full animate-progress-shrink ${
                  toastMessage.type === 'error' ? 'bg-danger/80' : toastMessage.type === 'success' ? 'bg-success/80' : 'bg-primary/80'
                }`}
                style={{ animationDuration: `${TOAST_DURATION}ms` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
