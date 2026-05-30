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

const ASSISTANT_DELTA_FLUSH_MS = 8;
const ASSISTANT_DELTA_FLUSH_CHARS = 16;
const TOOL_CALL_LINE_RE = /^\s{2,}\w[\w-]*\s*\(.*\)\s*$/;

function stripToolCallLines(text: string): string {
  const lines = text.split('\n');
  const filtered = lines.filter((line) => !TOOL_CALL_LINE_RE.test(line));
  return filtered.length > 0 ? filtered.join('\n') : text;
}

type Option = { value: string; label: string; active?: boolean };

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
  effortOptions: Option[];
  modelOptions: Option[];
  busy: boolean;
  ready: boolean;
  showThinking: boolean;
  todoItems: TodoItemSnapshot[];
  pendingToolCalls: PendingToolCall[];
  swarmTeammates: SwarmTeammateSnapshot[];
  swarmNotifications: SwarmNotificationSnapshot[];
  bgAgentLabel: string | null;
  commandResult: { text: string; type: 'success' | 'error' | 'info' } | null;
  connected: boolean;
  sessions: { value: string; label: string }[];
  deleteSessions: { value: string; label: string }[];
  clearDeleteSessions: () => void;
  clearModal: () => void;
  clearSelectModal: () => void;
  clearCommandResult: () => void;
  markSuppressCommandResult: () => void;
  setBusyTrue: () => void;
  requestSelectCommand: (command: string) => void;
  selectModalCommand: string | null;
  selectModalOptions: Option[];
  setEffortValue: (value: string) => void;
  setModelValue: (value: string) => void;
  sendRequest: (payload: Record<string, unknown>) => void;
  clearStaticItems: () => void;
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
  const [effortOptions, setEffortOptions] = useState<Option[]>([]);
  const [modelOptions, setModelOptions] = useState<Option[]>([]);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [showThinking, setShowThinking] = useState(true);
  const [todoItems, setTodoItems] = useState<TodoItemSnapshot[]>([]);
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[]>([]);
  const [swarmTeammates, setSwarmTeammates] = useState<SwarmTeammateSnapshot[]>([]);
  const [swarmNotifications, setSwarmNotifications] = useState<SwarmNotificationSnapshot[]>([]);
  const [bgAgentLabel, setBgAgentLabel] = useState<string | null>(null);
  const [commandResult, setCommandResult] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);
  const [connected, setConnected] = useState(false);
  const [sessions, setSessions] = useState<{ value: string; label: string }[]>([]);
  const [deleteSessions, setDeleteSessions] = useState<{ value: string; label: string }[]>([]);
  const [selectModalCommand, setSelectModalCommand] = useState<string | null>(null);
  const [selectModalOptions, setSelectModalOptions] = useState<Option[]>([]);
  const pendingSelectCommandRef = useRef<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const assistantBufferRef = useRef('');
  const pendingAssistantDeltaRef = useRef('');
  const assistantFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reasoningBufferRef = useRef('');
  const rawBufferRef = useRef('');
  const assistantFlushedForToolRef = useRef(false);
  const pendingToolCallsRef = useRef<PendingToolCall[]>([]);
  const showThinkingRef = useRef(true);
  const suppressNextCommandResultRef = useRef(false);
  const pendingInfoCommandRef = useRef<string | null>(null);

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
  const clearSelectModal = useCallback((): void => { setSelectModalCommand(null); setSelectModalOptions([]); pendingSelectCommandRef.current = null; }, []);
  const clearCommandResult = useCallback((): void => { setCommandResult(null); }, []);
  const markSuppressCommandResult = useCallback((): void => { suppressNextCommandResultRef.current = true; }, []);
  const requestSelectCommand = useCallback((command: string): void => {
    pendingSelectCommandRef.current = command;
    sendRequest({ type: 'select_command', command });
  }, [sendRequest]);

  const setEffortValue = useCallback((value: string): void => {
    // 与 terminal 端一致：用 apply_select_command 发送选择结果
    sendRequest({ type: 'apply_select_command', command: 'effort', value });
  }, [sendRequest]);

  const setModelValue = useCallback((value: string): void => {
    // 与 terminal 端一致：用 apply_select_command 发送选择结果
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
        // 连接后自动获取 skills/plugins/rules 信息
        setTimeout(() => {
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN) {
            pendingInfoCommandRef.current = 'skills';
            ws.send(JSON.stringify({ type: 'submit_line', line: '/skills' }));
          }
        }, 300);
        return;
      }
      if (evt.type === 'state_snapshot') {
        const newState = evt.state ?? {};
        // 检测 model/effort 变化，重新请求选项以同步 active 标记
        const oldModel = typeof status.model === 'string' ? status.model : '';
        const newModel = typeof newState.model === 'string' ? newState.model : '';
        if (newModel && newModel !== oldModel) {
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'select_command', command: 'model' }));
        }
        const oldEffort = typeof status.effort === 'string' ? status.effort : '';
        const newEffort = typeof newState.effort === 'string' ? newState.effort : '';
        if (newEffort && newEffort !== oldEffort) {
          const ws = wsRef.current;
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'select_command', command: 'effort' }));
        }
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
        // 推入 tool 项（携带 tool_input，供 toolInputMap 摘要显示）
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
        setStaticItems((evt.items as TranscriptItem[]).filter((i) => !(i.role === 'user' && i.text.startsWith('/'))));
        clearAssistantDelta(); pendingToolCallsRef.current = []; setPendingToolCalls([]); return;
      }

      // === 选择请求 ===
      if (evt.type === 'select_request') {
        const m = evt.modal ?? {};
        const cmd = String(m.command ?? '');
        const rawOpts = evt.select_options ?? [];
        const wasExplicit = pendingSelectCommandRef.current === cmd;
        pendingSelectCommandRef.current = null;

        if (cmd === 'resume') { setSessions(rawOpts.map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? '') }))); setBusy(false); return; }
        if (cmd === 'delete') { setDeleteSessions(rawOpts.map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? '') }))); setBusy(false); return; }
        if (cmd === 'effort') {
          const opts = rawOpts.map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? ''), active: o.active === true }));
          setEffortOptions(opts);
          if (wasExplicit && opts.length > 0) { setSelectModalCommand(cmd); setSelectModalOptions(opts); }
          setBusy(false); return;
        }
        if (cmd === 'model') {
          const opts = rawOpts.map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? ''), active: o.active === true }));
          setModelOptions(opts);
          if (wasExplicit && opts.length > 0) { setSelectModalCommand(cmd); setSelectModalOptions(opts); }
          setBusy(false); return;
        }
        if (cmd === 'permissions') {
          const activeMode = rawOpts.find((o) => o.active)?.value;
          if (activeMode) setStatus((s) => ({ ...s, permission_mode: activeMode }));
          if (wasExplicit && rawOpts.length > 0) {
            const opts = rawOpts.map((o) => ({ value: String(o.value ?? ''), label: String(o.label ?? ''), active: o.active === true }));
            setSelectModalCommand(cmd); setSelectModalOptions(opts);
          }
          setBusy(false); return;
        }
        setBusy(false); return;
      }

      // === 其他 ===
      if (evt.type === 'modal_request') { setModal(evt.modal ?? null); return; }
      if (evt.type === 'error') { pushStatic({ role: 'system', text: `error: ${evt.message ?? 'unknown error'}` }); clearAssistantDelta(); setBusy(false); return; }
      if (evt.type === 'todo_update' && evt.todo_items != null) { setTodoItems(evt.todo_items); return; }
      if (evt.type === 'swarm_status') { if (evt.swarm_teammates != null) setSwarmTeammates(evt.swarm_teammates); if (evt.swarm_notifications != null) setSwarmNotifications((prev) => [...prev, ...evt.swarm_notifications!].slice(-20)); return; }
      if (evt.type === 'plan_mode_change' && evt.plan_mode != null) { setStatus((s) => ({ ...s, permission_mode: evt.plan_mode })); return; }
      if (evt.type === 'command_result' && evt.command_result_data) {
        if (suppressNextCommandResultRef.current) { suppressNextCommandResultRef.current = false; return; }
        const msg = evt.command_result_data.message ?? '';
        const pending = pendingInfoCommandRef.current;
        if (pending) {
          pendingInfoCommandRef.current = null;
          if (pending === 'skills') {
            setSkills(_parseSkillsResult(msg));
            // 链式获取下一个
            setTimeout(() => {
              const ws = wsRef.current;
              if (ws && ws.readyState === WebSocket.OPEN) {
                pendingInfoCommandRef.current = 'plugins';
                ws.send(JSON.stringify({ type: 'submit_line', line: '/plugin list' }));
              }
            }, 100);
            return;
          }
          if (pending === 'plugins') {
            setPlugins(_parsePluginsResult(msg));
            setTimeout(() => {
              const ws = wsRef.current;
              if (ws && ws.readyState === WebSocket.OPEN) {
                pendingInfoCommandRef.current = 'rules';
                ws.send(JSON.stringify({ type: 'submit_line', line: '/rules' }));
              }
            }, 100);
            return;
          }
          if (pending === 'rules') {
            setRules(_parseRulesResult(msg));
            return;
          }
        }
        setCommandResult({ text: evt.command_result_data.message, type: evt.command_result_data.type || 'info' }); return;
      }
      if (evt.type === 'bg_agent_status') { setBgAgentLabel(evt.message ?? null); return; }
      if (evt.type === 'shutdown') { ws.close(); }
    }

    return () => { ws.close(); wsRef.current = null; };
  }, [url, pushStatic, flushAssistantDelta, clearAssistantDelta]);

  return useMemo(() => ({
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, effortOptions, modelOptions, busy, ready, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, commandResult, connected, sessions, deleteSessions,
    clearDeleteSessions, clearModal, clearSelectModal, clearCommandResult, markSuppressCommandResult,
    selectModalCommand, selectModalOptions, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
  }), [
    staticItems, assistantBuffer, streamingReasoning, status, tasks, commands,
    mcpServers, skills, plugins, rules, modal, effortOptions, modelOptions, busy, ready, showThinking,
    todoItems, pendingToolCalls, swarmTeammates, swarmNotifications,
    bgAgentLabel, commandResult, connected, sessions, deleteSessions,
    clearDeleteSessions, clearModal, clearSelectModal, clearCommandResult, markSuppressCommandResult,
    selectModalCommand, selectModalOptions, requestSelectCommand,
    setEffortValue, setModelValue, sendRequest, clearStaticItems, setBusyTrue,
  ]);
}

// ---- 命令结果解析器 ----

function _parseSkillsResult(text: string): SkillSnapshot[] {
  const skills: SkillSnapshot[] = [];
  for (const line of text.split('\n')) {
    // 主格式: "- name [source]: description"
    const m = line.match(/^-?\s*(.+?)\s*\[(\w+)\]\s*:\s*(.*)$/);
    if (m) {
      skills.push({ name: m[1]!.trim(), description: m[3]!.trim(), source: m[2]!.trim() });
      continue;
    }
    // 回退格式: "- name [source]"（无描述）
    const m2 = line.match(/^-?\s*(.+?)\s*\[(\w+)\]\s*$/);
    if (m2) {
      skills.push({ name: m2[1]!.trim(), description: '', source: m2[2]!.trim() });
    }
  }
  return skills;
}

function _parsePluginsResult(text: string): PluginSnapshot[] {
  const plugins: PluginSnapshot[] = [];
  for (const line of text.split('\n')) {
    // "- name [enabled/disabled]"
    const m = line.match(/^-?\s*(.+?)\s*\[(\w+)\]\s*$/);
    if (m) {
      plugins.push({
        name: m[1]!.trim(),
        description: '',
        enabled: m[2] === 'enabled',
        skill_count: 0, mcp_count: 0, command_count: 0,
      });
    }
  }
  return plugins;
}

function _parseRulesResult(text: string): RuleSnapshot[] {
  const rules: RuleSnapshot[] = [];
  for (const line of text.split('\n')) {
    // "  1. name  —  preview"
    const m = line.match(/^\s*\d+\.\s*(.+?)\s*[—-]/);
    if (m) {
      rules.push({ name: m[1]!.trim(), source: 'project' });
    }
  }
  return rules;
}
