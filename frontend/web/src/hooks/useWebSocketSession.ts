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
  showThinking: boolean;
  todoItems: TodoItemSnapshot[];
  pendingToolCalls: PendingToolCall[];
  swarmTeammates: SwarmTeammateSnapshot[];
  swarmNotifications: SwarmNotificationSnapshot[];
  bgAgentLabel: string | null;
  connected: boolean;
  sessions: { value: string; label: string }[];
  deleteSessions: { value: string; label: string }[];
  /** 正在恢复的会话 ID（null 表示无恢复进行中） */
  restoringSessionId: string | null;
  /** 设置正在恢复的会话 ID */
  setRestoringSessionId: (id: string | null) => void;
  clearDeleteSessions: () => void;
  suppressInlineOptions: () => void;
  suppressCommandResult: (count?: number) => void;
  suppressTranscript: (duration?: number) => void;
  clearModal: () => void;
  setBusyTrue: () => void;
  requestSelectCommand: (command: string) => void;
  setEffortValue: (value: string) => void;
  setModelValue: (value: string) => void;
  sendRequest: (payload: Record<string, unknown>) => void;
  clearStaticItems: () => void;
  setOnSelectRequest: (fn: ((payload: SelectRequestPayload) => void) | null) => void;
  setOnCommandResult: (fn: ((text: string, type: string) => void) | null) => void;
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
  const [sessions, setSessions] = useState<{ value: string; label: string }[]>([]);
  const [deleteSessions, setDeleteSessions] = useState<{ value: string; label: string }[]>([]);
  // 正在恢复的会话 ID（用于显示加载动画），由发出恢复请求时即设置
  const [restoringSessionId, setRestoringSessionId] = useState<string | null>(null);

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
  const onCommandResultRef = useRef<((text: string, type: string) => void) | null>(null);
  const suppressInlineRef = useRef(false);
  const suppressCommandResultCountRef = useRef(0);
  const suppressTranscriptRef = useRef(false);

  const setOnSelectRequest = useCallback((fn: ((payload: SelectRequestPayload) => void) | null) => { onSelectRequestRef.current = fn; }, []);
  const setOnCommandResult = useCallback((fn: ((text: string, type: string) => void) | null) => { onCommandResultRef.current = fn; }, []);
  const suppressInlineOptions = useCallback(() => { suppressInlineRef.current = true; }, []);
  const suppressCommandResult = useCallback((count: number = 1) => { suppressCommandResultCountRef.current += count; }, []);
  const suppressTranscript = useCallback(() => {
    suppressTranscriptRef.current = true;
  }, []);

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

  const setBusyTrue = useCallback((): void => { setBusy(true); }, []);

  const clearStaticItems = useCallback((): void => { setStaticItems([]); clearAssistantDelta(); }, [clearAssistantDelta]);
  const clearDeleteSessions = useCallback((): void => { setDeleteSessions([]); }, []);
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

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setReady(false); };
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
        return;
      }

      // === 转录 ===
      if (evt.type === 'transcript_item' && evt.item) {
        if (evt.item.role === 'user' && evt.item.text.startsWith('/')) return;
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
        if (pendingIdx !== -1) {
          const pending = pendingToolCallsRef.current[pendingIdx]!;
          toolName = pending.tool_name || toolName; toolInput = pending.tool_input || toolInput;
          pendingToolCallsRef.current = pendingToolCallsRef.current.filter((p) => p.tool_use_id !== toolUseId);
          setPendingToolCalls(pendingToolCallsRef.current);
        }
        pushStatic({ role: 'tool', text: toolName, tool_name: toolName, tool_input: toolInput, tool_use_id: toolUseId || undefined });
        pushStatic({ ...evt.item, role: 'tool_result', tool_name: toolName,
          tool_use_id: toolUseId || undefined, is_error: (evt.item.is_error ?? evt.is_error ?? undefined) as boolean | undefined });
        return;
      }
      if (evt.type === 'tool_input_updated') {
        const uid = evt.tool_use_id;
        pendingToolCallsRef.current = pendingToolCallsRef.current.map((p) => p.tool_use_id === uid ? { ...p, tool_input: evt.tool_input ?? undefined } : p);
        setPendingToolCalls(pendingToolCallsRef.current);
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
        setStaticItems((evt.items as TranscriptItem[]).filter((i) => !(i.role === 'user' && i.text.startsWith('/'))));
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
        // 恢复完成：清除加载动画并一次性替换转录
        setRestoringSessionId(null);
        const items = (evt.items ?? []) as TranscriptItem[];
        setStaticItems(items.filter((i) => !(i.role === 'user' && i.text.startsWith('/'))));
        clearAssistantDelta();
        pendingToolCallsRef.current = [];
        setPendingToolCalls([]);
        // 同步工具栏状态（model/effort/permission_mode 全部对齐恢复的会话）
        if (evt.state) setStatus(evt.state as Record<string, unknown>);
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
        // B 通道精细化指令结果：在 transcript 区域渲染，不走 command_result toast
        const payload = evt.web_query_payload;
        if (evt.web_query_kind === 'text' && typeof payload === 'string') {
          if (payload.trim()) pushStatic({ role: 'system', text: payload });
        } else if (evt.web_query_kind === 'transcript_replace' && Array.isArray(payload)) {
          setStaticItems((payload as TranscriptItem[]).filter((i) => !(i.role === 'user' && i.text.startsWith('/'))));
        }
        setBusy(false);
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
          onCommandResultRef.current(msg, evt.command_result_data.type || 'info');
        }
        return;
      }
      if (evt.type === 'bg_agent_status') { setBgAgentLabel(evt.message ?? null); return; }
      if (evt.type === 'shutdown') { ws.close(); }
    }

    return () => { ws.close(); wsRef.current = null; };
  }, [url, pushStatic, flushAssistantDelta, clearAssistantDelta]);

  return useMemo(() => ({
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, modelOptions, busy, ready, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, connected, sessions, deleteSessions, restoringSessionId, setRestoringSessionId, clearDeleteSessions, suppressInlineOptions,
    suppressCommandResult, suppressTranscript, clearModal, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
    setOnSelectRequest, setOnCommandResult,
  }), [
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, modelOptions, busy, ready, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, connected, sessions, deleteSessions, restoringSessionId, clearDeleteSessions, suppressInlineOptions,
    suppressCommandResult, suppressTranscript, clearModal, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
    setOnSelectRequest, setOnCommandResult,
  ]);
}
