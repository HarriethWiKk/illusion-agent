import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type {
  BackendEvent,
  McpServerSnapshot,
  PendingToolCall,
  SelectRequestPayload,
  SwarmNotificationSnapshot,
  SwarmTeammateSnapshot,
  TaskSnapshot,
  TodoItemSnapshot,
  TranscriptItem,
} from '../types/protocol';

const ASSISTANT_DELTA_FLUSH_MS = 16;
const ASSISTANT_DELTA_FLUSH_CHARS = 32;

const TOOL_CALL_LINE_RE = /^\s{2,}\w[\w-]*\s*\(.*\)\s*$/;

function stripToolCallLines(text: string): string {
  const lines = text.split('\n');
  const filtered = lines.filter((line) => !TOOL_CALL_LINE_RE.test(line));
  return filtered.length > 0 ? filtered.join('\n') : text;
}

export interface WebSocketSessionState {
  staticItems: TranscriptItem[];
  assistantBuffer: string;
  status: Record<string, unknown>;
  tasks: TaskSnapshot[];
  commands: string[];
  mcpServers: McpServerSnapshot[];
  modal: Record<string, unknown> | null;
  selectRequest: SelectRequestPayload | null;
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
  sendRequest: (payload: Record<string, unknown>) => void;
  clearStaticItems: () => void;
}

export function useWebSocketSession(url: string): WebSocketSessionState {
  const [staticItems, setStaticItems] = useState<TranscriptItem[]>([]);
  const [assistantBuffer, setAssistantBuffer] = useState('');
  const [status, setStatus] = useState<Record<string, unknown>>({});
  const [tasks, setTasks] = useState<TaskSnapshot[]>([]);
  const [commands, setCommands] = useState<string[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServerSnapshot[]>([]);
  const [modal, setModal] = useState<Record<string, unknown> | null>(null);
  const [selectRequest, setSelectRequest] = useState<SelectRequestPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [showThinking, setShowThinking] = useState(true);
  const [todoItems, setTodoItems] = useState<TodoItemSnapshot[]>([]);
  const [pendingToolCalls, setPendingToolCalls] = useState<PendingToolCall[]>([]);
  const [swarmTeammates, setSwarmTeammates] = useState<SwarmTeammateSnapshot[]>([]);
  const [swarmNotifications, setSwarmNotifications] = useState<SwarmNotificationSnapshot[]>([]);
  const [bgAgentLabel, setBgAgentLabel] = useState<string | null>(null);
  const [commandResult, setCommandResult] = useState<{
    text: string;
    type: 'success' | 'error' | 'info';
  } | null>(null);
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const assistantBufferRef = useRef('');
  const pendingAssistantDeltaRef = useRef('');
  const assistantFlushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reasoningBufferRef = useRef('');
  const rawBufferRef = useRef('');
  const assistantFlushedForToolRef = useRef(false);
  const pendingToolCallsRef = useRef<PendingToolCall[]>([]);
  const showThinkingRef = useRef(true);

  const pushStatic = useCallback((item: TranscriptItem): void => {
    setStaticItems((prev) => [...prev, item]);
  }, []);

  const flushAssistantDelta = useCallback((): void => {
    const pending = pendingAssistantDeltaRef.current;
    if (!pending) return;
    pendingAssistantDeltaRef.current = '';
    rawBufferRef.current += pending;

    let displayText = rawBufferRef.current;
    const think = showThinkingRef.current;
    if (!think) {
      displayText = displayText
        .replace(/<think\b[^>]*>[\s\S]*?<\/think\b[^>]*>/gi, '')
        .replace(/<\/think\b[^>]*>/gi, '')
        .replace(/<think\b[^>]*>/gi, '')
        .replace(/<th(?:i(?:n(?:k)?)?)?\s*$/i, '');
    } else {
      displayText = displayText
        .replace(/<think\b[^>]*>/gi, '')
        .replace(/<\/think\b[^>]*>/gi, '')
        .replace(/<th(?:i(?:n(?:k)?)?)?\s*$/i, '');
    }
    if (think && reasoningBufferRef.current.trim()) {
      const reasoning = reasoningBufferRef.current.trim();
      const text = displayText.trim();
      displayText = text ? `${reasoning}\n\n${text}` : reasoning;
    }
    assistantBufferRef.current = displayText;
    setAssistantBuffer(displayText);
  }, []);

  const clearAssistantDelta = useCallback((): void => {
    pendingAssistantDeltaRef.current = '';
    assistantBufferRef.current = '';
    rawBufferRef.current = '';
    if (assistantFlushTimerRef.current) {
      clearTimeout(assistantFlushTimerRef.current);
      assistantFlushTimerRef.current = null;
    }
    setAssistantBuffer('');
    reasoningBufferRef.current = '';
  }, []);

  const sendRequest = useCallback((payload: Record<string, unknown>): void => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(payload));
  }, []);

  const clearStaticItems = useCallback((): void => {
    setStaticItems([]);
    clearAssistantDelta();
  }, [clearAssistantDelta]);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setReady(false);
    };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event) => {
      let parsed: BackendEvent;
      try {
        parsed = JSON.parse(event.data as string) as BackendEvent;
      } catch {
        return;
      }
      handleEvent(parsed);
    };

    function handleEvent(evt: BackendEvent): void {
      if (evt.type === 'ready') {
        setReady(true);
        setStatus(evt.state ?? {});
        const st = evt.state?.show_thinking;
        if (typeof st === 'boolean') {
          setShowThinking(st);
          showThinkingRef.current = st;
        }
        setTasks(evt.tasks ?? []);
        setCommands(evt.commands ?? []);
        setMcpServers((evt.mcp_servers as McpServerSnapshot[]) ?? []);
        return;
      }
      if (evt.type === 'state_snapshot') {
        setStatus(evt.state ?? {});
        const st = evt.state?.show_thinking;
        if (typeof st === 'boolean') {
          setShowThinking(st);
          showThinkingRef.current = st;
        }
        setMcpServers((evt.mcp_servers as McpServerSnapshot[]) ?? []);
        return;
      }
      if (evt.type === 'tasks_snapshot') {
        setTasks(evt.tasks ?? []);
        return;
      }
      if (evt.type === 'transcript_item' && evt.item) {
        pushStatic(evt.item as TranscriptItem);
        return;
      }
      if (evt.type === 'assistant_delta') {
        assistantFlushedForToolRef.current = false;
        if (evt.reasoning) {
          reasoningBufferRef.current += evt.reasoning;
        }
        const delta = evt.message ?? '';
        if (!delta) {
          if (showThinkingRef.current && reasoningBufferRef.current.trim()) {
            const display = reasoningBufferRef.current.trim();
            assistantBufferRef.current = display;
            setAssistantBuffer(display);
          }
          return;
        }
        pendingAssistantDeltaRef.current += delta;
        if (pendingAssistantDeltaRef.current.length >= ASSISTANT_DELTA_FLUSH_CHARS) {
          flushAssistantDelta();
          return;
        }
        if (!assistantFlushTimerRef.current) {
          assistantFlushTimerRef.current = setTimeout(() => {
            assistantFlushTimerRef.current = null;
            flushAssistantDelta();
          }, ASSISTANT_DELTA_FLUSH_MS);
        }
        return;
      }
      if (evt.type === 'assistant_complete') {
        if (assistantFlushTimerRef.current) {
          clearTimeout(assistantFlushTimerRef.current);
          assistantFlushTimerRef.current = null;
        }
        flushAssistantDelta();
        if (!assistantFlushedForToolRef.current) {
          const text = evt.message ?? rawBufferRef.current;
          const reasoning = (evt.reasoning ?? reasoningBufferRef.current) || undefined;
          if (text.trim() || (reasoning ?? '').trim()) {
            pushStatic({ role: 'assistant', text: stripToolCallLines(text), reasoning });
          }
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
      if ((evt.type === 'tool_started' || evt.type === 'tool_completed') && evt.item) {
        if (evt.type === 'tool_started') {
          if (rawBufferRef.current.trim() || pendingAssistantDeltaRef.current || reasoningBufferRef.current.trim()) {
            if (assistantFlushTimerRef.current) {
              clearTimeout(assistantFlushTimerRef.current);
              assistantFlushTimerRef.current = null;
            }
            flushAssistantDelta();
            const text = rawBufferRef.current;
            const reasoning = reasoningBufferRef.current || undefined;
            if (text.trim() || (reasoning ?? '').trim()) {
              pushStatic({ role: 'assistant', text: stripToolCallLines(text), reasoning });
            }
            clearAssistantDelta();
            assistantFlushedForToolRef.current = true;
          }
          setBusy(true);
          const toolInput = evt.item.tool_input ?? evt.tool_input;
          const toolUseId = evt.item.tool_use_id ?? evt.tool_use_id ?? '';
          const pendingCall: PendingToolCall = {
            tool_name: evt.item.tool_name ?? evt.tool_name ?? 'tool',
            tool_use_id: toolUseId,
            tool_input: (toolInput && Object.keys(toolInput as Record<string, unknown>).length > 0) ? toolInput as Record<string, unknown> : undefined,
          };
          pendingToolCallsRef.current = [...pendingToolCallsRef.current, pendingCall];
          setPendingToolCalls(pendingToolCallsRef.current);
          return;
        }
        // tool_completed
        const toolUseId = evt.item.tool_use_id ?? evt.tool_use_id ?? '';
        const pendingIdx = pendingToolCallsRef.current.findIndex((p) => p.tool_use_id === toolUseId);
        if (pendingIdx !== -1) {
          const pending = pendingToolCallsRef.current[pendingIdx]!;
          pendingToolCallsRef.current = pendingToolCallsRef.current.filter((p) => p.tool_use_id !== toolUseId);
          setPendingToolCalls(pendingToolCallsRef.current);
          pushStatic({
            role: 'tool',
            text: pending.tool_name,
            tool_name: pending.tool_name,
            tool_input: pending.tool_input,
            tool_use_id: pending.tool_use_id || undefined,
          });
        }
        const enrichedItem: TranscriptItem = {
          ...evt.item,
          tool_name: evt.item.tool_name ?? evt.tool_name ?? undefined,
          tool_input: (evt.item.tool_input ?? undefined) as Record<string, unknown> | undefined,
          tool_use_id: (evt.item.tool_use_id ?? evt.tool_use_id ?? undefined) as string | undefined,
          is_error: (evt.item.is_error ?? evt.is_error ?? undefined) as boolean | undefined,
        };
        pushStatic(enrichedItem);
        return;
      }
      if (evt.type === 'tool_input_updated') {
        const uid = evt.tool_use_id;
        pendingToolCallsRef.current = pendingToolCallsRef.current.map((p) =>
          p.tool_use_id === uid ? { ...p, tool_input: evt.tool_input ?? undefined } : p,
        );
        setPendingToolCalls(pendingToolCallsRef.current);
        return;
      }
      if (evt.type === 'clear_transcript') {
        setStaticItems([]);
        clearAssistantDelta();
        pendingToolCallsRef.current = [];
        setPendingToolCalls([]);
        return;
      }
      if (evt.type === 'replace_transcript' && evt.items) {
        const newItems = (evt.items as TranscriptItem[]).filter((item: TranscriptItem) => {
          return !(item.role === 'user' && item.text.startsWith('/'));
        });
        setStaticItems(newItems);
        clearAssistantDelta();
        pendingToolCallsRef.current = [];
        setPendingToolCalls([]);
        return;
      }
      if (evt.type === 'select_request') {
        const m = evt.modal ?? {};
        setSelectRequest({
          title: String(m.title ?? 'Select'),
          command: String(m.command ?? ''),
          options: evt.select_options ?? [],
        });
        setBusy(false);
        return;
      }
      if (evt.type === 'modal_request') {
        setModal(evt.modal ?? null);
        return;
      }
      if (evt.type === 'error') {
        pushStatic({ role: 'system', text: `error: ${evt.message ?? 'unknown error'}` });
        clearAssistantDelta();
        setBusy(false);
        return;
      }
      if (evt.type === 'todo_update' && evt.todo_items != null) {
        setTodoItems(evt.todo_items);
        return;
      }
      if (evt.type === 'swarm_status') {
        if (evt.swarm_teammates != null) setSwarmTeammates(evt.swarm_teammates);
        if (evt.swarm_notifications != null)
          setSwarmNotifications((prev) => [...prev, ...evt.swarm_notifications!].slice(-20));
        return;
      }
      if (evt.type === 'plan_mode_change' && evt.plan_mode != null) {
        setStatus((s) => ({ ...s, permission_mode: evt.plan_mode }));
        return;
      }
      if (evt.type === 'command_result' && evt.command_result_data) {
        setCommandResult({ text: evt.command_result_data.message, type: evt.command_result_data.type || 'info' });
        return;
      }
      if (evt.type === 'bg_agent_status') {
        setBgAgentLabel(evt.message ?? null);
        return;
      }
      if (evt.type === 'shutdown') {
        ws.close();
      }
    }

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [url, pushStatic, flushAssistantDelta, clearAssistantDelta]);

  return useMemo(
    () => ({
      staticItems,
      assistantBuffer,
      status,
      tasks,
      commands,
      mcpServers,
      modal,
      selectRequest,
      busy,
      ready,
      showThinking,
      todoItems,
      pendingToolCalls,
      swarmTeammates,
      swarmNotifications,
      bgAgentLabel,
      commandResult,
      connected,
      sendRequest,
      clearStaticItems,
    }),
    [
      assistantBuffer, bgAgentLabel, busy, commandResult, commands, connected,
      mcpServers, modal, pendingToolCalls, ready, selectRequest, showThinking,
      staticItems, status, swarmNotifications, swarmTeammates, tasks, todoItems,
      sendRequest, clearStaticItems,
    ],
  );
}
