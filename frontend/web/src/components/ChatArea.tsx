/**
 * @fileoverview 聊天区域组件
 *
 * Web 前端的主要对话显示区域，负责：
 * - 显示对话历史（按轮次分组）
 * - 显示待处理的工具调用
 * - 显示流式回复和思考过程
 * - 显示权限确认和问答模态框
 * - 自动滚动到底部
 *
 * @module ChatArea
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';
import MessageBubble, { PendingToolBubble, StreamingBuffer, ReasoningContent } from './MessageBubble';
import WelcomeScreen from './WelcomeScreen';
import { PermissionCard, QuestionCard } from './ModalCard';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

/** 消息列表收缩阈值：超过此轮次时折叠更早的消息 */
const COLLAPSE_TURN_THRESHOLD = 5;
/** 判定"已在底部"的像素容差 */
const BOTTOM_THRESHOLD_PX = 80;

/**
 * 将一轮对话的 items 拆分为三部分：
 * - userItems：用户消息（始终可见）
 * - thinkingItems：工具调用 + 中间 assistant 消息（归入"思考过程"可折叠区）
 * - finalAssistant：最后一条含文本的 assistant 消息（始终可见，其 reasoning 归入思考区）
 *
 * 流式阶段（streaming=true）所有 assistant 消息都视作思考过程的一部分：
 * 最终回复由 StreamingBuffer 实时展示，避免中间 LLM 消息被误判为最终回复，
 * 导致后续工具调用显示在消息上方、以及复制/回退按钮闪烁等问题。
 *
 * @param items - 单轮转录项列表
 * @param streaming - 是否处于流式输出阶段
 * @returns 拆分结果
 */
function splitTurnItems(items: TranscriptItem[], streaming: boolean = false) {
  const userItems: TranscriptItem[] = [];
  const thinkingItems: TranscriptItem[] = [];
  let finalAssistant: TranscriptItem | null = null;

  // 流式阶段：所有 assistant 消息归入思考过程，不区分"最终回复"
  if (streaming) {
    for (const item of items) {
      if (item.role === 'user' || item.role === 'plan') {
        userItems.push(item);
      } else {
        thinkingItems.push(item);
      }
    }
    return { userItems, thinkingItems, finalAssistant };
  }

  // 完成态：找最后一条有非空 text 的 assistant 消息作为"最终回复"
  let lastAssistantIdx = -1;
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i]!.role === 'assistant' && items[i]!.text.trim()) {
      lastAssistantIdx = i;
      break;
    }
  }

  for (let i = 0; i < items.length; i++) {
    const item = items[i]!;
    if (item.role === 'user' || item.role === 'plan') {
      userItems.push(item);
    } else if (i === lastAssistantIdx) {
      finalAssistant = item;
    } else {
      thinkingItems.push(item);
    }
  }

  return { userItems, thinkingItems, finalAssistant };
}

/**
 * 思考过程折叠区组件
 *
 * 将一轮对话中的工具调用、中间 assistant 消息、最终 assistant 的 reasoning
 * 统一收纳进一个可折叠的"思考过程"区域，减少历史消息的浏览器渲染负担。
 *
 * 流式输出阶段（autoExpand=true）自动展开，完成后自动折叠。
 *
 * @param props.thinkingItems - 工具调用 + 中间消息
 * @param props.finalReasoning - 最终 assistant 的 reasoning 文本
 * @param props.lang - UI 语言
 * @param props.toolInputMap - 工具输入映射
 * @param props.autoExpand - 是否自动展开（流式阶段）
 */
function ThinkingProcessSection({
  thinkingItems,
  finalReasoning,
  lang,
  toolInputMap,
  autoExpand,
  onToggle,
}: {
  thinkingItems: TranscriptItem[];
  finalReasoning?: string;
  lang: UiLanguage;
  toolInputMap: Map<string, Record<string, unknown>>;
  autoExpand: boolean;
  onToggle?: () => void;
}) {
  const [open, setOpen] = useState(autoExpand);
  const prevAutoExpand = useRef(autoExpand);

  // autoExpand 变化时（流式开始/结束）自动同步展开状态
  if (autoExpand !== prevAutoExpand.current) {
    prevAutoExpand.current = autoExpand;
    setOpen(autoExpand);
  }

  const hasContent = thinkingItems.length > 0 || !!finalReasoning?.trim();
  if (!hasContent) return null;

  const stepCount = thinkingItems.length + (finalReasoning?.trim() ? 1 : 0);
  const label = t(lang, 'thinking_process_count').replace('{count}', String(stepCount));

  const handleToggle = () => {
    setOpen(!open);
    onToggle?.();
  };

  return (
    <div className="my-1">
      {autoExpand ? (
        // 流式输出阶段：仅显示标题，不渲染可点击的折叠按钮，避免用户误操作
        <div className="flex items-center gap-1.5 text-xs text-content-secondary py-1">
          <svg className="w-3 h-3 rotate-90" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4.5 2.5L8 6L4.5 9.5" />
          </svg>
          <span className="font-medium">{label}</span>
        </div>
      ) : (
        <button
          onClick={handleToggle}
          className="flex items-center gap-1.5 text-xs text-content-secondary hover:text-content-primary transition-colors py-1 cursor-pointer"
        >
          <svg
            className={`w-3 h-3 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4.5 2.5L8 6L4.5 9.5" />
          </svg>
          <span className="font-medium">{label}</span>
        </button>
      )}
      {open && (
        <div className="mt-1.5 animate-fade-in-up">
          {thinkingItems.map((item, idx) => (
            <MessageBubble key={idx} item={item} toolInputMap={toolInputMap} lang={lang} showActions={false} inlineReasoning />
          ))}
          {finalReasoning?.trim() && <ReasoningContent text={finalReasoning} />}
        </div>
      )}
    </div>
  );
}

/**
 * 从 staticItems 中提取 tool_use_id → tool_input 映射
 *
 * @param items - 转录项列表
 * @returns tool_use_id 到 tool_input 的映射
 */
function buildToolInputMap(items: TranscriptItem[]): Map<string, Record<string, unknown>> {
  const map = new Map<string, Record<string, unknown>>();
  for (const item of items) {
    if (item.role === 'tool' && item.tool_use_id && item.tool_input) {
      map.set(item.tool_use_id, item.tool_input);
    }
  }
  return map;
}

/**
 * ChatArea 组件属性接口
 */
interface ChatAreaProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 静态转录项列表 */
  staticItems: TranscriptItem[];
  /** 助手回复缓冲区 */
  assistantBuffer: string;
  /** 流式推理文本 */
  streamingReasoning: string;
  /** 待处理的工具调用列表 */
  pendingToolCalls: PendingToolCall[];
  /** 是否忙碌 */
  busy: boolean;
  /** 是否已连接 */
  connected: boolean;
  /** 模态对话框配置 */
  modal: Record<string, unknown> | null;
  /** 权限响应回调 */
  onPermissionResponse: (requestId: string, allowed: boolean, alwaysAllow: boolean, toolName: string) => void;
  /** 问答响应回调 */
  onQuestionResponse: (requestId: string, answer: string) => void;
  /** 正在恢复的会话 ID（可选，非空时显示居中加载卡片覆盖转录区） */
  restoringSessionId?: string | null;
  /** 撤销到指定轮次回调（参数为待回退轮次数） */
  onRewindToTurn?: (turnsToRewind: number) => void;
  /** 重新生成回调（回退最后一轮并重发 user 消息） */
  onRegenerate?: () => void;
}

/**
 * 聊天区域组件
 *
 * Web 前端的主要对话显示区域。
 *
 * @param props - 组件属性
 * @returns 返回聊天区域的 JSX 元素
 */
export default function ChatArea({
  lang, staticItems, assistantBuffer, streamingReasoning, pendingToolCalls, busy, connected,
  modal, onPermissionResponse, onQuestionResponse, restoringSessionId, onRewindToTurn, onRegenerate,
}: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const userScrolledUpRef = useRef(false);

  // 按用户消息分组为轮次(turn)，每轮以用户消息开头
  // 注意：hooks 必须在任何条件返回之前调用（React Rules of Hooks）
  const turns = useMemo(() => {
    const result: TranscriptItem[][] = [];
    for (const item of staticItems) {
      if (item.role === 'user' || result.length === 0) {
        result.push([item]);
      } else {
        result[result.length - 1]!.push(item);
      }
    }
    return result;
  }, [staticItems]);

  // 消息列表收缩：超过阈值时仅展示最新 N 轮，其余折叠
  const { visibleTurns, hiddenCount } = useMemo(() => {
    if (expanded || turns.length <= COLLAPSE_TURN_THRESHOLD) {
      return { visibleTurns: turns, hiddenCount: 0 };
    }
    return {
      visibleTurns: turns.slice(turns.length - COLLAPSE_TURN_THRESHOLD),
      hiddenCount: turns.length - COLLAPSE_TURN_THRESHOLD,
    };
  }, [turns, expanded]);

  // 计算可见轮次在原 turns 中的起始偏移
  const turnOffset = turns.length - visibleTurns.length;

  // tool_use_id → tool_input 映射，用于 tool_result 摘要显示
  const toolInputMap = useMemo(() => buildToolInputMap(staticItems), [staticItems]);

  /** 检查滚动容器是否在底部附近 */
  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    const max = el.scrollHeight - el.clientHeight;
    return el.scrollTop >= max - BOTTOM_THRESHOLD_PX;
  }, []);

  /** 滚动事件处理：跟踪用户是否手动上滑 */
  const handleScroll = useCallback(() => {
    const nearBottom = isNearBottom();
    userScrolledUpRef.current = !nearBottom;
    setShowScrollDown(!nearBottom && scrollRef.current ? scrollRef.current.scrollHeight - scrollRef.current.clientHeight > 200 : false);
  }, [isNearBottom]);

  /** 一键回到底部 */
  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    userScrolledUpRef.current = false;
    setShowScrollDown(false);
  }, []);

  // 内容变化时自动滚动到底部（仅当用户未手动上滑时）
  useEffect(() => {
    if (userScrolledUpRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [staticItems, assistantBuffer, streamingReasoning, pendingToolCalls, modal]);

  // 用户发送新消息时强制回到底部（忽略用户是否手动上滑过）
  const userMsgCount = useMemo(() => staticItems.filter((i) => i.role === 'user').length, [staticItems]);
  const prevUserMsgCountRef = useRef(0);
  useEffect(() => {
    if (userMsgCount > prevUserMsgCountRef.current) {
      userScrolledUpRef.current = false;
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    }
    prevUserMsgCountRef.current = userMsgCount;
  }, [userMsgCount]);

  // 新会话或恢复后重置展开状态
  useEffect(() => {
    setExpanded(false);
    userScrolledUpRef.current = false;
  }, [staticItems.length === 0]);

  const hasContent = staticItems.length > 0 || assistantBuffer || streamingReasoning || pendingToolCalls.length > 0 || !!modal;

  // 会话恢复中：显示居中加载卡片，覆盖正常转录区
  // 此条件返回在所有 hooks 之后，不违反 React Rules of Hooks
  if (restoringSessionId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <svg className="animate-spin w-8 h-8 text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm text-content-secondary">{t(lang, 'restoring_session')}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto relative" ref={scrollRef} onScroll={handleScroll}>
      {!connected && !hasContent && (
        <div className="flex items-center justify-center h-full text-content-disabled text-sm font-medium">
          {t(lang, 'connecting')}
        </div>
      )}
      {connected && !hasContent && (
        <WelcomeScreen lang={lang} />
      )}

      <div className="mx-auto max-w-5xl px-6 md:px-10 lg:px-16 py-6">
        {/* 折叠的更早消息入口 */}
        {hiddenCount > 0 && (
          <div className="flex justify-center mb-6">
            <button
              onClick={() => setExpanded(true)}
              className="px-4 py-2 text-sm text-content-secondary hover:text-content-primary glass-surface rounded-full transition-colors cursor-pointer hover:scale-105 active:scale-95"
            >
              {t(lang, 'show_earlier').replace('{count}', String(hiddenCount))}
            </button>
          </div>
        )}

        {visibleTurns.map((turn, visIdx) => {
          const turnIdx = turnOffset + visIdx;
          const isLastTurn = turnIdx === turns.length - 1;
          const autoExpand = busy && isLastTurn;
          const { userItems, thinkingItems, finalAssistant } = splitTurnItems(turn, autoExpand);
          const turnsToRewind = turns.length - turnIdx;
          return (
            <div key={turnIdx} className={visIdx > 0 ? 'mt-12' : ''}>
              {userItems.map((item, msgIdx) => (
                <MessageBubble
                  key={`u-${turnIdx}-${msgIdx}`}
                  item={item}
                  lang={lang}
                  onRewind={onRewindToTurn ? () => onRewindToTurn(turnsToRewind) : undefined}
                  actionsDisabled={busy}
                />
              ))}
              <ThinkingProcessSection
                thinkingItems={thinkingItems}
                finalReasoning={finalAssistant?.reasoning}
                lang={lang}
                toolInputMap={toolInputMap}
                autoExpand={autoExpand}
                onToggle={isLastTurn ? () => {
                  // 切换折叠后延迟滚动到底部，等待 DOM 更新完成
                  setTimeout(() => {
                    const el = scrollRef.current;
                    if (el) el.scrollTop = el.scrollHeight;
                  }, 0);
                } : undefined}
              />
              {finalAssistant && (
                <MessageBubble
                  key={`f-${turnIdx}`}
                  item={finalAssistant}
                  toolInputMap={toolInputMap}
                  lang={lang}
                  hideReasoning
                  onRegenerate={isLastTurn ? onRegenerate : undefined}
                  actionsDisabled={busy}
                />
              )}
            </div>
          );
        })}
        {pendingToolCalls.length > 0 && (
          <div className={turns.length > 0 ? 'mt-4' : ''}>
            {pendingToolCalls.map((call) => (
              <PendingToolBubble key={call.tool_use_id} call={call} />
            ))}
          </div>
        )}
        {busy && !assistantBuffer && !streamingReasoning && pendingToolCalls.length === 0 && (
          <div className={turns.length > 0 ? 'mt-4' : ''}>
            <ThinkingIndicator lang={lang} />
          </div>
        )}
        {busy && (assistantBuffer || streamingReasoning) && (
          <div className={turns.length > 0 ? 'mt-4' : ''}>
            <StreamingBuffer text={assistantBuffer} reasoning={streamingReasoning} />
          </div>
        )}
        {modal?.kind === 'permission' && (
          <PermissionCard modal={modal} lang={lang} onRespond={onPermissionResponse} />
        )}
        {modal?.kind === 'question' && (
          <QuestionCard modal={modal} lang={lang} onRespond={onQuestionResponse} />
        )}
      </div>

      {/* 一键回到底部浮动按钮 */}
      {showScrollDown && (
        <button
          onClick={scrollToBottom}
          className="fixed bottom-36 left-1/2 -translate-x-1/2 z-30 w-9 h-9 flex items-center justify-center rounded-full glass-surface text-content-secondary hover:text-content-primary shadow-lg transition-all duration-200 hover:scale-110 active:scale-95 cursor-pointer animate-fade-in-up"
          title={t(lang, 'scroll_to_bottom')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12l7 7 7-7" />
          </svg>
        </button>
      )}
    </div>
  );
}

function ThinkingIndicator({ lang }: { lang: UiLanguage }) {
  return (
    <div className="flex items-center gap-2.5 py-2">
      <span className="flex gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-primary animate-bounce" style={{ animationDelay: '300ms' }} />
      </span>
      <span className="text-xs text-content-secondary animate-pulse">
        {t(lang, 'thinking')}
      </span>
    </div>
  );
}
