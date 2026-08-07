/**
 * @fileoverview WebSocket 会话管理 Hook
 *
 * 本模块提供了 useWebSocketSession Hook，用于管理与后端的 WebSocket 通信会话。
 * 主要功能包括：
 * - 建立和维护 WebSocket 连接
 * - 处理后端发送的 JSON 协议事件
 * - 管理会话状态（转录项、任务、命令等）
 * - 处理助手流式回复的缓冲和刷新
 * - 管理工具调用的生命周期
 * - 处理模态对话框和选择请求
 *
 * @module useWebSocketSession
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type {
  BackendEvent,
  McpServerSnapshot,
  PendingToolCall,
  PluginSnapshot,
  RuleSnapshot,
  SkillSnapshot,
  SwarmNotificationSnapshot,
  SwarmTeammateSnapshot,
  TaskSnapshot,
  TodoItemSnapshot,
  TranscriptItem,
} from '../types/protocol';

/**
 * 助手流式回复刷新间隔（毫秒）
 * 控制助手回复文本在屏幕上的更新频率
 */
const ASSISTANT_DELTA_FLUSH_MS = 8;

/**
 * 助手流式回复刷新字符阈值
 * 当缓冲的字符数达到此值时立即刷新
 */
const ASSISTANT_DELTA_FLUSH_CHARS = 16;

/**
 * 工具调用行匹配正则表达式
 *
 * 匹配模型可能嵌入在助手文本中的工具调用预览行。
 * 例如："  bash (git add ...)" 或 "read (file_path: ...)"
 */
const TOOL_CALL_LINE_RE = /^\s{2,}\w[\w-]*\s*\(.*\)\s*$/;

/**
 * 从助手文本中移除工具调用预览行
 *
 * @param text - 原始助手文本
 * @returns 移除工具调用行后的文本
 */
function stripToolCallLines(text: string): string {
  const lines = text.split('\n');
  const filtered = lines.filter((line) => !TOOL_CALL_LINE_RE.test(line));
  return filtered.length > 0 ? filtered.join('\n') : text;
}

/**
 * 选项类型
 */
type Option = { value: string; label: string; active?: boolean };

/**
 * 选择请求载荷类型
 *
 * 后端发送到前端的选择请求，用于显示选择模态对话框。
 */
export type SelectRequestPayload = {
  /** 关联的命令名称 */
  command: string;
  /** 对话框标题 */
  title: string;
  /** 可选项列表 */
  options: Array<{ value: string; label: string; description?: string; active?: boolean }>;
};

/**
 * WebSocket 会话状态接口
 *
 * 定义了 useWebSocketSession Hook 返回的所有状态和操作方法。
 */
export interface WebSocketSessionState {
  staticItems: TranscriptItem[];
  assistantBuffer: string;
  streamingReasoning: string;
  status: Record<string, unknown>;
  tasks: TaskSnapshot[];
  commands: string[];
  mcpServers: McpServerSnapshot[];
  skills: SkillSnapshot[];
  plugins: PluginSnapshot[];
  rules: RuleSnapshot[];
  modal: Record<string, unknown> | null;
  modelOptions: Option[];
  busy: boolean;
  ready: boolean;
  /** 首次登录标识（后端 ready 事件携带，无 env_N 且无 working_directory 时为 true） */
  firstLogin: boolean;
  showThinking: boolean;
  todoItems: TodoItemSnapshot[];
  pendingToolCalls: PendingToolCall[];
  swarmTeammates: SwarmTeammateSnapshot[];
  swarmNotifications: SwarmNotificationSnapshot[];
  bgAgentLabel: string | null;
  connected: boolean;
  sessions: { value: string; label: string }[];
  /** 正在恢复的会话 ID（null 表示无恢复进行中） */
  restoringSessionId: string | null;
  /** 设置正在恢复的会话 ID */
  setRestoringSessionId: (id: string | null) => void;
  /** 模型是否正在切换中 */
  modelSwitching: boolean;
  /** 设置模型切换状态 */
  setModelSwitching: (v: boolean) => void;
  // ---- btw 侧问相关 ----
  /** 侧问请求进行中 */
  btwLoading: boolean;
  /** 侧问回复文本（非 null 表示成功回复） */
  btwReply: string | null;
  /** 侧问错误文本（非空表示失败） */
  btwError: string | null;
  /** 当前活跃的 btw 请求 ID */
  btwRequestId: string | null;
  /** 发送侧问请求：生成 request_id 并发 btw_request */
  sendBtwRequest: (question: string) => void;
  /** 取消侧问请求：发 btw_cancel 并清空本地 btw 状态 */
  sendBtwCancel: (requestId: string) => void;
  /** 清空所有 btw 状态（关闭卡片时调用） */
  clearBtwState: () => void;
  // ---- agent 向导相关 ----
  /** agent 向导可选工具列表（来自 agent_wizard_init_response） */
  agentWizardTools: { name: string; description: string }[] | null;
  /** agent 向导可选模型列表（来自 agent_wizard_init_response，后端返回 name 字段） */
  agentWizardModels: { name: string; label: string }[] | null;
  /** LLM 生成的 agent 草稿（来自 agent_generate_response） */
  agentGenerated: { identifier: string; when_to_use: string; system_prompt: string } | null;
  /** agent 生成中标志 */
  agentGenerateLoading: boolean;
  /** agent 生成错误文本 */
  agentGenerateError: string | null;
  /** agent 向导提交结果（来自 agent_wizard_result） */
  agentWizardResult: { success: boolean; path?: string; errors?: Record<string, string>; error?: string } | null;
  /** 请求初始化 agent 向导：发 agent_wizard_init */
  sendAgentWizardInit: () => void;
  /** 请求 LLM 生成 agent 草稿：生成 request_id，发 agent_generate_request，置 loading */
  sendAgentGenerateRequest: (prompt: string, model: string) => void;
  /** 提交 agent 向导表单：发 agent_wizard_submit */
  sendAgentWizardSubmit: (fields: Record<string, unknown>, scope: 'user' | 'project') => void;
  /** 清空所有 agent 向导状态（关闭表单时调用） */
  clearAgentWizardState: () => void;
  /** 首次登录配置保存后清除 firstLogin 状态 */
  clearFirstLogin: () => void;
  deleteSessions: (sessionIds: string[], deleteAll?: boolean) => void;
  clearModal: () => void;
  setBusyTrue: () => void;
  requestSelectCommand: (command: string) => void;
  setEffortValue: (value: string) => void;
  setModelValue: (value: string) => void;
  sendRequest: (payload: Record<string, unknown>) => void;
  /** 停止请求已发送、等待后端确认（按钮旋转动画），line_complete 后清除 */
  stopping: boolean;
  /** 发送停止请求（自动管理 stopping 状态与超时兜底） */
  sendStop: () => void;
  clearStaticItems: () => void;
  setOnSelectRequest: (fn: ((payload: SelectRequestPayload) => void) | null) => void;
  setOnCommandResult: (fn: ((text: string, type: string, requestId?: string) => void) | null) => void;
  /** 注册版本更新提醒回调（update_available 事件触发，参数为最新版本号） */
  setOnUpdateAvailable: (fn: ((latestVersion: string) => void) | null) => void;
}

export function useWebSocketSession(url: string): WebSocketSessionState {
  const [staticItems, setStaticItems] = useState<TranscriptItem[]>([]);
  const [assistantBuffer, setAssistantBuffer] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [tasks, setTasks] = useState<TaskSnapshot[]>([]);
  const [commands, setCommands] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServerSnapshot[]>([]);
  const [skills, setSkills] = useState<SkillSnapshot[]>([]);
  const [plugins, setPlugins] = useState<PluginSnapshot[]>([]);
  const [rules, setRules] = useState<RuleSnapshot[]>([]);
  const [modal, setModal] = useState<Record<string, unknown> | null>(null);
  const [modelOptions, setModelOptions] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [showThinking, setShowThinking] = useState(true);
  const [todoItems, setTodoItems] = useState<TodoItemSnapshot[]>([]);
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[]>([]);
  const [swarmTeammates, setSwarmTeammates] = useState<SwarmTeammateSnapshot[]>([]);
  const [swarmNotifications, setSwarmNotifications] = useState<SwarmNotificationSnapshot[]>([]);
  const [bgAgentLabel, setBgAgentLabel] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  /** 首次登录标识（后端 ready 事件携带，无 env_N 且无 working_directory 时为 true） */
  const [firstLogin, setFirstLogin] = useState(false);
  const [sessions, setSessions] = useState<{ value: string; label: string }[]>([]);
  // 正在恢复的会话 ID（用于显示加载动画），由发出恢复请求时即设置
  const [restoringSessionId, setRestoringSessionId] = useState<string | null>(null);
  // 模型切换中（用于 Toolbar 显示加载动画）
  const [modelSwitching, setModelSwitching] = useState(false);
  // 停止请求已发送、等待后端确认（按钮显示旋转动画）。由 line_complete 清除
  // （不依赖 busy 变化——后台任务场景 busy 恒为 false，busy 监听会漏清除）。
  const [stopping, setStopping] = useState(false);
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearStopTimer = useCallback((): void => {
    if (stopTimerRef.current !== null) {
      clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
  }, []);

  // ---- btw 侧问相关状态 ----
  /** 侧问请求进行中 */
  const [btwLoading, setBtwLoading] = useState(false);
  /** 侧问回复文本 */
  const [btwReply, setBtwReply] = useState<string | null>(null);
  /** 侧问错误文本 */
  const [btwError, setBtwError] = useState<string | null>(null);
  /** 当前活跃的 btw 请求 ID（用于响应匹配与取消） */
  const [btwRequestId, setBtwRequestId] = useState<string | null>(null);
  /** btw 请求 ID 的 ref：handleEvent 闭包中读取当前活跃 ID，避免过期响应覆盖新请求状态 */
  const btwRequestIdRef = useRef<string | null>(null);

  // ---- agent 向导相关状态 ----
  /** agent 向导可选工具列表 */
  const [agentWizardTools, setAgentWizardTools] = useState<{ name: string; description: string }[] | null>(null);
  /** agent 向导可选模型列表 */
  const [agentWizardModels, setAgentWizardModels] = useState<{ name: string; label: string }[] | null>(null);
  /** LLM 生成的 agent 草稿 */
  const [agentGenerated, setAgentGenerated] = useState<{ identifier: string; when_to_use: string; system_prompt: string } | null>(null);
  /** agent 生成中标志 */
  const [agentGenerateLoading, setAgentGenerateLoading] = useState(false);
  /** agent 生成错误文本 */
  const [agentGenerateError, setAgentGenerateError] = useState<string | null>(null);
  /** agent 向导提交结果 */
  const [agentWizardResult, setAgentWizardResult] = useState<{ success: boolean; path?: string; errors?: Record<string, string>; error?: string } | null>(null);
  /** agent generate 请求 ID 的 ref：handleEvent 闭包中读取当前活跃 ID，避免过期响应覆盖新请求状态 */
  const agentGenerateRequestIdRef = useRef<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const assistantBufferRef = useRef('');
  const pendingAssistantDeltaRef = useRef('');
  const assistantFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reasoningBufferRef = useRef('');
  const rawBufferRef = useRef('');
  const assistantFlushedForToolRef = useRef(false);
  const pendingToolCallsRef = useRef<PendingToolCall[]>([]);
  const showThinkingRef = useRef(true);

  // 回调 refs：App 注入，用于 select_request 和 command_result 事件
  const onSelectRequestRef = useRef<((payload: SelectRequestPayload) => void) | null>(null);
  const onCommandResultRef = useRef<((text: string, type: string, requestId?: string) => void) | null>(null);
  const onUpdateAvailableRef = useRef<((latestVersion: string) => void) | null>(null);
  const suppressCommandResultCountRef = useRef(0);
  const suppressTranscriptRef = useRef(false);

  const setOnSelectRequest = useCallback((fn: ((payload: SelectRequestPayload) => void) | null) => { onSelectRequestRef.current = fn; }, []);
  const setOnCommandResult = useCallback((fn: ((text: string, type: string) => void) | null) => { onCommandResultRef.current = fn; }, []);
  const setOnUpdateAvailable = useCallback((fn: ((latestVersion: string) => void) | null) => { onUpdateAvailableRef.current = fn; }, []);
  // suppress 方法不再导出，仅内部使用（refs 保留用于 transcript_item/replace_transcript/command_result 处理）

  const pushStatic = useCallback((item: TranscriptItem): void => {
    setStaticItems((prev) => [...prev, item]);
  }, []);

  const flushAssistantDelta = useCallback((): void => {
    const pending = pendingAssistantDeltaRef.current;
    if (!pending) return;
    pendingAssistantDeltaRef.current = '';
    rawBufferRef.current += pending;
    let displayText = rawBufferRef.current
      .replace(/<think\b[^>]*>[\s\S]*?<\/think\b[^>]*>/gi, '')
      .replace(/<\/think\b[^>]*>/gi, '')
      .replace(/<think\b[^>]*>/gi, '')
      .replace(/<th(?:i(?:n(?:k)?)?)?\s*$/i, '');
    assistantBufferRef.current = displayText;
    setAssistantBuffer(displayText);
  }, []);

  const clearAssistantDelta = useCallback((): void => {
    pendingAssistantDeltaRef.current = '';
    assistantBufferRef.current = '';
    rawBufferRef.current = '';
    if (assistantFlushTimerRef.current) { clearTimeout(assistantFlushTimerRef.current); assistantFlushTimerRef.current = null; }
    setAssistantBuffer('');
    reasoningBufferRef.current = '';
    setStreamingReasoning('');
  }, []);

  const sendRequest = useCallback((payload: Record<string, unknown>): void => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(payload));
  }, []);

  /** 发送停止请求：按钮进入旋转动画，直到后端确认（line_complete）清除；
   *  15s 超时兜底（后端异常挂起时避免按钮永久旋转） */
  const sendStop = useCallback((): void => {
    setStopping(true);
    clearStopTimer();
    stopTimerRef.current = setTimeout(() => {
      setStopping(false);
      stopTimerRef.current = null;
    }, 15000);
    sendRequest({ type: 'stop' });
  }, [sendRequest, clearStopTimer]);

  const setBusyTrue = useCallback((): void => { setBusy(true); }, []);

  const clearStaticItems = useCallback((): void => { setStaticItems([]); clearAssistantDelta(); }, [clearAssistantDelta]);
  const deleteSessions = useCallback((sessionIds: string[], deleteAll: boolean = false): void => {
    // 立即从本地状态中移除
    if (deleteAll) {
      setSessions([]);
    } else {
      setSessions(prev => prev.filter(s => !sessionIds.includes(s.value)));
    }

    // 发送删除请求到后端
    sendRequest({
      type: 'web_delete_sessions',
      session_ids: sessionIds,
      delete_all: deleteAll,
    });
  }, [sendRequest]);
  const clearModal = useCallback((): void => { setModal(null); }, []);
  const requestSelectCommand = useCallback((command: string): void => {
    sendRequest({ type: 'select_command', command });
  }, [sendRequest]);

  const setEffortValue = useCallback((value: string): void => {
    sendRequest({ type: 'apply_select_command', command: 'effort', value });
  }, [sendRequest]);

  const setModelValue = useCallback((value: string): void => {
    sendRequest({ type: 'apply_select_command', command: 'model', value });
  }, [sendRequest]);

  /**
   * 发送 btw 侧问请求
   *
   * 生成 request_id（优先用 crypto.randomUUID，不可用时回退到时间戳+随机串兜底），
   * 发送 btw_request 并将本地状态置为 loading。同时清空上一次的 reply/error。
   *
   * @param question - 侧问问题文本
   */
  const sendBtwRequest = useCallback((question: string): void => {
    const requestId = (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
      ? crypto.randomUUID()
      : `btw-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    btwRequestIdRef.current = requestId;
    setBtwRequestId(requestId);
    setBtwLoading(true);
    setBtwReply(null);
    setBtwError(null);
    sendRequest({ type: 'btw_request', question, request_id: requestId });
  }, [sendRequest]);

  /**
   * 取消进行中的 btw 请求
   *
   * 向后端发送 btw_cancel 并清空本地 btw 状态。
   * 当 requestId 为空（无活跃请求）时静默忽略，避免无意义请求。
   *
   * @param requestId - 要取消的 btw 请求 ID
   */
  const sendBtwCancel = useCallback((requestId: string): void => {
    if (requestId) {
      sendRequest({ type: 'btw_cancel', request_id: requestId });
    }
    btwRequestIdRef.current = null;
    setBtwLoading(false);
    setBtwReply(null);
    setBtwError(null);
    setBtwRequestId(null);
  }, [sendRequest]);

  /**
   * 清空所有 btw 状态
   *
   * 关闭卡片时调用，仅清空本地展示状态，不向后端发取消请求。
   * 进行中的请求若需取消，调用方应先调用 sendBtwCancel。
   */
  const clearBtwState = useCallback((): void => {
    btwRequestIdRef.current = null;
    setBtwLoading(false);
    setBtwReply(null);
    setBtwError(null);
    setBtwRequestId(null);
  }, []);

  /**
   * 请求初始化 agent 向导
   *
   * 触发后端返回 agent_wizard_init_response（工具列表 + 模型列表）。
   */
  const sendAgentWizardInit = useCallback((): void => {
    sendRequest({ type: 'agent_wizard_init' });
  }, [sendRequest]);

  /**
   * 请求 LLM 生成 agent 草稿
   *
   * 生成 request_id（优先用 crypto.randomUUID，不可用时回退到时间戳+随机串兜底），
   * 发送 agent_generate_request 并将本地状态置为 loading。同时清空上一次的草稿/错误。
   *
   * @param prompt - 用户输入的描述性提示词
   * @param model - 使用的模型名称（'inherit' 表示继承当前会话模型）
   */
  const sendAgentGenerateRequest = useCallback((prompt: string, model: string): void => {
    const requestId = (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
      ? crypto.randomUUID()
      : `agent-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    agentGenerateRequestIdRef.current = requestId;
    setAgentGenerateLoading(true);
    setAgentGenerateError(null);
    setAgentGenerated(null);
    sendRequest({ type: 'agent_generate_request', prompt, model, request_id: requestId });
  }, [sendRequest]);

  /**
   * 提交 agent 向导表单
   *
   * @param fields - 表单字段（name/description/system_prompt/model/tools 等）
   * @param scope - 写入范围：'user' 或 'project'
   */
  const sendAgentWizardSubmit = useCallback((fields: Record<string, unknown>, scope: 'user' | 'project'): void => {
    sendRequest({ type: 'agent_wizard_submit', fields, scope });
  }, [sendRequest]);

  /**
   * 清空所有 agent 向导相关状态
   *
   * 重置工具/模型列表、生成草稿、提交结果、生成 loading 与错误，
   * 用于关闭表单或重新打开时避免残留旧数据干扰新一次填写。
   */
  const clearAgentWizardState = useCallback((): void => {
    agentGenerateRequestIdRef.current = null;
    setAgentWizardTools(null);
    setAgentWizardModels(null);
    setAgentGenerated(null);
    setAgentWizardResult(null);
    setAgentGenerateLoading(false);
    setAgentGenerateError(null);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setReady(false);
      setFirstLogin(false);
      setRestoringSessionId(null);
    };
    ws.onerror = () => setConnected(false);
    ws.onmessage = (event) => {
      let parsed: BackendEvent;
      try { parsed = JSON.parse(event.data as string) as BackendEvent; } catch { return; }
      handleEvent(parsed);
    };

    function handleEvent(evt: BackendEvent): void {
      // === 状态 ===
      if (evt.type === 'ready') {
        setReady(true);
        setFirstLogin(evt.first_login ?? false);
        setStatus(evt.state ?? {});
        const st = evt.state?.show_thinking;
        if (typeof st === 'boolean') { setShowThinking(st); showThinkingRef.current = st; }
        setTasks(evt.tasks ?? []);
        setCommands(evt.commands ?? []);
        setMcpServers((evt.mcp_servers as McpServerSnapshot[]) ?? []);
        // 会话列表、skills/plugins/rules、模型选项均由后端在 ready 后主动推送
        // （web_sessions / web_resources / web_models），无需前端 setTimeout 拉取
        return;
      }
      if (evt.type === 'state_snapshot') {
        const newState = evt.state ?? {};
        // 工具栏状态权威来源：web_setting_changed 即时更新 + state_snapshot 兜底合并。
        // 移除旧的"status.model/effort 变化时主动发 select_command 重新拉选项"补偿逻辑，
        // 模型选项改由后端 web_models 推送驱动。
        setStatus(newState);
        const st = newState.show_thinking;
        if (typeof st === 'boolean') { setShowThinking(st); showThinkingRef.current = st; }
        setMcpServers((evt.mcp_servers as McpServerSnapshot[]) ?? []);
        return;
      }
      if (evt.type === 'tasks_snapshot') { setTasks(evt.tasks ?? []); return; }
      if (evt.type === 'update_available' && evt.latest_version) {
        onUpdateAvailableRef.current?.(evt.latest_version);
        return;
      }

      // === 流式 ===
      if (evt.type === 'assistant_delta') {
        assistantFlushedForToolRef.current = false;
        setBusy(true);
        if (evt.reasoning) { reasoningBufferRef.current += evt.reasoning; setStreamingReasoning(reasoningBufferRef.current); }
        const delta = evt.message ?? '';
        if (!delta) return;
        pendingAssistantDeltaRef.current += delta;
        if (pendingAssistantDeltaRef.current.length >= ASSISTANT_DELTA_FLUSH_CHARS) { flushAssistantDelta(); return; }
        if (!assistantFlushTimerRef.current) {
          assistantFlushTimerRef.current = setTimeout(() => { assistantFlushTimerRef.current = null; flushAssistantDelta(); }, ASSISTANT_DELTA_FLUSH_MS);
        }
        return;
      }
      if (evt.type === 'assistant_complete') {
        if (assistantFlushTimerRef.current) { clearTimeout(assistantFlushTimerRef.current); assistantFlushTimerRef.current = null; }
        flushAssistantDelta();
        if (!assistantFlushedForToolRef.current) {
          const text = evt.message ?? rawBufferRef.current;
          const reasoning = (evt.reasoning ?? reasoningBufferRef.current) || undefined;
          if (text.trim() || (reasoning ?? '').trim()) pushStatic({ role: 'assistant', text: stripToolCallLines(text), reasoning });
        }
        assistantFlushedForToolRef.current = false;
        clearAssistantDelta();
        return;
      }
      if (evt.type === 'line_complete') {
        clearAssistantDelta();
        pendingToolCallsRef.current = [];
        setPendingToolCalls([]);
        setBgAgentLabel(null);
        setBusy(false);
        // 停止确认：清除按钮旋转动画（含超时定时器）
        setStopping(false);
        clearStopTimer();
        return;
      }

      // === 转录 ===
      if (evt.type === 'transcript_item' && evt.item) {
        // 过滤 / 开头的 user 消息：这些是 apply_select_command → _process_line 产生的
        // 命令产物（如 /context set 512000），不是真实用户输入，不应显示在会话中
        if (evt.item.role === 'user' && evt.item.text.startsWith('/')) return;
        // 过滤后台任务完成通知（<task-notification> XML）：注入给 LLM 的系统消息，
        // 不应作为真实用户消息显示
        if (evt.item.role === 'user' && evt.item.text.startsWith('<task-notification>')) return;
        if (suppressTranscriptRef.current) return;
        pushStatic(evt.item as TranscriptItem);
        return;
      }

      // === 工具 ===
      if ((evt.type === 'tool_started' || evt.type === 'tool_completed') && evt.item) {
        if (evt.type === 'tool_started') {
          if (rawBufferRef.current.trim() || pendingAssistantDeltaRef.current || reasoningBufferRef.current.trim()) {
            if (assistantFlushTimerRef.current) { clearTimeout(assistantFlushTimerRef.current); assistantFlushTimerRef.current = null; }
            flushAssistantDelta();
            const text = rawBufferRef.current;
            const reasoning = reasoningBufferRef.current || undefined;
            if (text.trim() || (reasoning ?? '').trim()) pushStatic({ role: 'assistant', text: stripToolCallLines(text), reasoning });
            clearAssistantDelta();
            assistantFlushedForToolRef.current = true;
          }
          setBusy(true);
          const toolInput = evt.item.tool_input ?? evt.tool_input;
          const toolUseId = evt.item.tool_use_id ?? evt.tool_use_id ?? '';
          pendingToolCallsRef.current = [...pendingToolCallsRef.current, {
            tool_name: evt.item.tool_name ?? evt.tool_name ?? 'tool', tool_use_id: toolUseId,
            tool_input: (toolInput && Object.keys(toolInput as Record<string, unknown>).length > 0) ? toolInput as Record<string, unknown> : undefined,
          }];
          setPendingToolCalls(pendingToolCallsRef.current);
          return;
        }
        const toolUseId = evt.item.tool_use_id ?? evt.tool_use_id ?? '';
        const pendingIdx = pendingToolCallsRef.current.findIndex((p) => p.tool_use_id === toolUseId);
        let toolName = evt.item.tool_name ?? evt.tool_name ?? 'tool';
        let toolInput = (evt.item.tool_input ?? undefined) as Record<string, unknown> | undefined;
        // 完成时从 pending 保留流式进度（agent 思考过程），随 tool_result 折叠展示
        let progressMessages: Array<{message: string; type?: string}> | undefined;
        if (pendingIdx !== -1) {
          const pending = pendingToolCallsRef.current[pendingIdx]!;
          toolName = pending.tool_name || toolName; toolInput = pending.tool_input || toolInput;
          progressMessages = pending.progressMessages;
          pendingToolCallsRef.current = pendingToolCallsRef.current.filter((p) => p.tool_use_id !== toolUseId);
          setPendingToolCalls(pendingToolCallsRef.current);
        }
        pushStatic({ role: 'tool', text: toolName, tool_name: toolName, tool_input: toolInput, tool_use_id: toolUseId || undefined });
        pushStatic({ ...evt.item, role: 'tool_result', tool_name: toolName,
          tool_use_id: toolUseId || undefined, is_error: (evt.item.is_error ?? evt.is_error ?? undefined) as boolean | undefined,
          progress_messages: progressMessages });
        return;
      }
      if (evt.type === 'tool_input_updated') {
        const uid = evt.tool_use_id;
        pendingToolCallsRef.current = pendingToolCallsRef.current.map((p) => p.tool_use_id === uid ? { ...p, tool_input: evt.tool_input ?? undefined } : p);
        setPendingToolCalls(pendingToolCallsRef.current);
        return;
      }
      // 流式进度消息：累积到对应 pendingToolCall 的 progressMessages（对称于 terminal 端）
      // thinking/text 为增量片段，累积到同类型最后一条；tool/status 为完整消息，直接追加
      if (evt.type === 'tool_progress') {
        const uid = evt.tool_use_id;
        if (uid) {
          const msgType = evt.progress_type ?? 'status';
          const msgContent = evt.message ?? '';
          pendingToolCallsRef.current = pendingToolCallsRef.current.map((p) => {
            if (p.tool_use_id !== uid) return p;
            const prev = p.progressMessages ?? [];
            let next;
            if (msgType === 'thinking' || msgType === 'text') {
              const lastIdx = prev.length - 1;
              const lastEntry = lastIdx >= 0 ? prev[lastIdx] : undefined;
              if (lastEntry && lastEntry.type === msgType) {
                next = [...prev];
                next[lastIdx] = {message: lastEntry.message + msgContent, type: msgType};
              } else {
                next = [...prev, {message: msgContent, type: msgType}];
              }
            } else {
              next = [...prev, {message: msgContent, type: msgType}];
            }
            // 累积全部进度（web 端不受 terminal 行数限制；pending 在
            // tool_completed 后即被丢弃，生命周期短，无内存风险）
            return {...p, progressMessages: next};
          });
          setPendingToolCalls(pendingToolCallsRef.current);
        }
        return;
      }

      // === 转录管理 ===
      if (evt.type === 'clear_transcript') { setStaticItems([]); clearAssistantDelta(); pendingToolCallsRef.current = []; setPendingToolCalls([]); return; }
      if (evt.type === 'replace_transcript' && evt.items) {
        // 检查是否需要抑制显示（用于左侧栏操作解耦）
        if (suppressTranscriptRef.current) {
          suppressTranscriptRef.current = false;
          return;
        }
        // 过滤 / 开头 user 消息与后台任务完成通知（<task-notification> XML）
        setStaticItems((evt.items as TranscriptItem[]).filter((item) => {
          if (item.role !== 'user') return true;
          if (item.text.startsWith('/')) return false;
          if (item.text.startsWith('<task-notification>')) return false;
          return true;
        }));
        clearAssistantDelta(); pendingToolCallsRef.current = []; setPendingToolCalls([]); return;
      }

      // === Web 专属推送事件（web_* 命名空间）===
      if (evt.type === 'web_sessions') {
        // 后端推送的会话列表，格式化为 sessions 状态
        const opts = (evt.web_sessions ?? []).map((o) => ({ value: String(o.id ?? ''), label: String(o.label ?? '') }));
        setSessions(opts);
        setBusy(false);
        return;
      }
      if (evt.type === 'web_restore_started') {
        // 恢复开始：动画由发出请求时即设置，此处无需重复设置
        return;
      }
      if (evt.type === 'web_restore_completed') {
        // 恢复完成（或失败）：始终清除加载动画
        setRestoringSessionId(null);
        clearAssistantDelta();
        pendingToolCallsRef.current = [];
        setPendingToolCalls([]);
        if (evt.web_error) {
          // 恢复失败：显示错误提示，不替换转录（保留当前内容）
          pushStatic({ role: 'system', text: `恢复会话失败: ${evt.web_error}` });
        } else {
          // 恢复成功：一次性替换转录（过滤历史中的命令产物 user 消息）
          const items = (evt.items ?? []) as TranscriptItem[];
          setStaticItems(items.filter((i) => !(i.role === 'user' && i.text.startsWith('/'))));
          // 同步工具栏状态（model/effort/permission_mode 全部对齐恢复的会话）
          if (evt.state) setStatus(evt.state as Record<string, unknown>);
        }
        return;
      }
      if (evt.type === 'web_setting_changed') {
        // 单项设置变更：合并到 status，前端工具栏读 status 字段即时更新
        const key = evt.setting_key;
        const value = evt.setting_value;
        if (key && value !== undefined && value !== null) {
          setStatus((s) => ({ ...s, [key]: value }));
        }
        return;
      }
      if (evt.type === 'web_models') {
        // 后端推送的模型选项，更新 modelOptions（含 active 态）
        const opts = (evt.web_models ?? []).map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? ''), active: o.active === true }));
        setModelOptions(opts);
        setModelSwitching(false); // 模型切换完成，清除加载态
        return;
      }
      if (evt.type === 'web_resources') {
        // 后端推送的资源快照，结构化更新（废弃旧的文本正则解析）
        const res = evt.web_resources;
        if (res) {
          setSkills((res.skills as SkillSnapshot[]) ?? []);
          setPlugins((res.plugins as PluginSnapshot[]) ?? []);
          setRules((res.rules as RuleSnapshot[]) ?? []);
          setMcpServers((res.mcp_servers as McpServerSnapshot[]) ?? []);
        }
        return;
      }
      if (evt.type === 'web_query_result') {
        const payload = evt.web_query_payload;
        if (evt.web_query_kind === 'text' && typeof payload === 'string') {
          // 所有 B 通道指令的文本结果统一走 toast，不渲染到主会话
          if (payload.trim() && onCommandResultRef.current) {
            onCommandResultRef.current(payload, 'info');
          }
        } else if (evt.web_query_kind === 'transcript_replace' && Array.isArray(payload)) {
          setStaticItems(payload as TranscriptItem[]);
        }
        setBusy(false);
        return;
      }

      // === btw 侧问响应 ===
      if (evt.type === 'btw_response') {
        // 无活跃请求时（用户已取消/关闭卡片）忽略所有迟到响应，
        // 避免在途的 btw_response 重新弹出已被用户主动关闭的卡片
        const activeId = btwRequestIdRef.current;
        if (!activeId) {
          return;
        }
        // 仅处理与当前活跃 request_id 匹配的响应，避免过期响应覆盖新请求状态
        if (evt.request_id && evt.request_id !== activeId) {
          return;
        }
        setBtwLoading(false);
        if (evt.error) {
          setBtwError(evt.error);
        } else if (evt.reply != null) {
          setBtwReply(evt.reply);
        }
        // 保留 btwRequestId 以便后续关闭卡片时仍可发 btw_cancel
        return;
      }

      // === agent 向导响应 ===
      if (evt.type === 'agent_wizard_init_response') {
        setAgentWizardTools(evt.tools ?? null);
        setAgentWizardModels(evt.models ?? null);
        return;
      }
      if (evt.type === 'agent_generate_response') {
        // 无活跃请求时（用户已关闭表单）忽略所有迟到响应
        const activeId = agentGenerateRequestIdRef.current;
        if (!activeId) {
          return;
        }
        // 仅处理与当前活跃 request_id 匹配的响应，避免过期响应覆盖新请求状态
        if (evt.request_id && evt.request_id !== activeId) {
          return;
        }
        setAgentGenerateLoading(false);
        if (evt.error) {
          setAgentGenerateError(evt.error);
          setAgentGenerated(null);
        } else if (evt.agent) {
          setAgentGenerateError(null);
          setAgentGenerated(evt.agent);
        }
        // 保留 agentGenerateRequestId 以便表单消费完成后由 clearAgentWizardState 清理
        return;
      }
      if (evt.type === 'agent_wizard_result') {
        setAgentWizardResult({
          success: Boolean(evt.success),
          path: evt.path ?? undefined,
          errors: evt.errors ?? undefined,
          error: evt.error ?? undefined,
        });
        return;
      }

      // === 选择请求 ===
      if (evt.type === 'select_request') {
        const m = evt.modal ?? {};
        const cmd = String(m.command ?? '');
        const rawOpts = evt.select_options ?? [];
        // 注：resume/delete/effort/model/permissions 分支已全部删除——会话管理转
        // web_restore_session/web_delete_sessions，设置类转 web_set_setting/web_models。
        // select_request 现仅服务 B 通道的 rewind/context 多步选择。

        // 其他命令（context、rewind 等）→ 通知 App 显示内联选项
        if (onSelectRequestRef.current) {
          const title = String(m.title ?? cmd);
          const options = rawOpts.map((o) => ({
            value: String(o.value ?? ''),
            label: String(o.label ?? ''),
            description: o.description ? String(o.description) : undefined,
            active: o.active === true,
          }));
          onSelectRequestRef.current({ command: cmd, title, options });
        }
        setBusy(false);
        return;
      }

      // === 其他 ===
      if (evt.type === 'modal_request') { setModal(evt.modal ?? null); return; }
      if (evt.type === 'error') { pushStatic({ role: 'system', text: `error: ${evt.message ?? 'unknown error'}` }); clearAssistantDelta(); setBusy(false); return; }
      if (evt.type === 'todo_update' && evt.todo_items != null) { setTodoItems(evt.todo_items); return; }
      if (evt.type === 'swarm_status') { if (evt.swarm_teammates != null) setSwarmTeammates(evt.swarm_teammates); if (evt.swarm_notifications != null) setSwarmNotifications((prev) => [...prev, ...evt.swarm_notifications!].slice(-20)); return; }
      if (evt.type === 'plan_mode_change' && evt.plan_mode != null) { setStatus((s) => ({ ...s, permission_mode: evt.plan_mode })); return; }
      if (evt.type === 'command_result' && evt.command_result_data) {
        const msg = evt.command_result_data.message ?? '';
        // skills/plugins/rules 已由后端 web_resources 推送驱动，
        // 移除旧的 pendingInfoCommand 链式发指令 + 文本正则解析逻辑
        // 检查是否需要抑制显示
        if (suppressCommandResultCountRef.current > 0) {
          suppressCommandResultCountRef.current--;
          return;
        }
        // 通知 App 显示 toast
        if (onCommandResultRef.current) {
          const reqId = evt.command_result_data?.request_id as string | undefined;
          onCommandResultRef.current(msg, evt.command_result_data.type || 'info', reqId);
        }
        return;
      }
      if (evt.type === 'bg_agent_status') { setBgAgentLabel(evt.message ?? null); return; }
      if (evt.type === 'shutdown') { ws.close(); }
    }

    return () => { ws.close(); wsRef.current = null; };
  }, [url, pushStatic, flushAssistantDelta, clearAssistantDelta]);

  // 首次登录配置保存后手动清除 firstLogin 状态（避免再次打开表单仍显示首次登录）
  const clearFirstLogin = useCallback(() => setFirstLogin(false), []);

  return useMemo(() => ({
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, modelOptions, busy, ready, firstLogin, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, connected, sessions, deleteSessions, restoringSessionId, setRestoringSessionId, clearModal, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
    setOnSelectRequest, setOnCommandResult, setOnUpdateAvailable,
    stopping, sendStop,
    modelSwitching, setModelSwitching,
    btwLoading, btwReply, btwError, btwRequestId,
    sendBtwRequest, sendBtwCancel, clearBtwState,
    agentWizardTools, agentWizardModels, agentGenerated, agentGenerateLoading,
    agentGenerateError, agentWizardResult,
    sendAgentWizardInit, sendAgentGenerateRequest, sendAgentWizardSubmit, clearAgentWizardState,
    clearFirstLogin,
  }), [
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, modelOptions, busy, ready, firstLogin, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, connected, sessions, deleteSessions, restoringSessionId, clearModal, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
    setOnSelectRequest, setOnCommandResult, setOnUpdateAvailable,
    stopping, sendStop,
    modelSwitching,
    btwLoading, btwReply, btwError, btwRequestId,
    sendBtwRequest, sendBtwCancel, clearBtwState,
    agentWizardTools, agentWizardModels, agentGenerated, agentGenerateLoading,
    agentGenerateError, agentWizardResult,
    sendAgentWizardInit, sendAgentGenerateRequest, sendAgentWizardSubmit, clearAgentWizardState,
    clearFirstLogin,
  ]);
}
