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

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { t, type UiLanguage } from '../i18n';
import MessageBubble, { PendingToolBubble, StreamingBuffer, ThinkingBlock } from './MessageBubble';
import WelcomeScreen from './WelcomeScreen';
import { PermissionCard, QuestionCard } from './ModalCard';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

/** 消息列表收缩阈值：超过此轮次时折叠更早的消息 */
const COLLAPSE_TURN_THRESHOLD = 5;
/** 判定"已在底部附近"的像素容差（自动跟随在此范围内才生效，参考 kimi-code） */
const FOLLOW_THRESHOLD_PX = 30;
/** 判定"用户已离开底部"的像素容差（超过此距离显示"回到底部"按钮） */
const BOTTOM_THRESHOLD_PX = 80;

/**
 * 将一轮对话的 items 拆分为三部分：
 * - userItems：用户消息（始终可见）
 * - thinkingItems：工具调用 + 中间 assistant 消息（各自独立折叠）
 * - finalAssistant：最后一条含文本的 assistant 消息（始终可见，其 reasoning 独立折叠）
 *
 * 流式阶段（streaming=true）所有 assistant 消息都视作中间消息：
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
  // plan 角色由 ModalCard 专门展示，不在对话流中重复显示
  if (streaming) {
    for (const item of items) {
      if (item.role === 'plan') {
        continue; // 跳过 plan 消息，由 ModalCard 处理
      }
      if (item.role === 'user') {
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
    if (item.role === 'plan') {
      continue; // 跳过 plan 消息，由 ModalCard 处理
    }
    if (item.role === 'user') {
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
 * "任务完成"折叠区组件（三级标题样式）
 *
 * 将一轮对话中最终回复之前的所有内容（中间 text、工具调用、思考过程、
 * 最终回复的思考过程）再折叠一次（二级折叠），折叠样式与普通折叠区分：
 * - 三级标题"任务完成 >"（展开后箭头变为向下"任务完成 ∨"），字号/字重/颜色
 *   与最终回复 markdown 渲染的 h3（.prose h3）保持一致
 * - 流式阶段标题显示"任务进行中"
 * - 标题下方是一条分隔直线
 *
 * 流式阶段自动展开（内容可见）；轮次完成（streaming=false）时自动折叠。
 * 用户手动操作过的折叠区不被自动状态覆盖（尊重用户选择）。
 *
 * @param props.streaming - 轮次是否仍在流式（流式展开、完成折叠）
 * @param props.lang - UI 语言
 * @param props.hasContent - 折叠内容是否非空（空内容时展开态不渲染内容区）
 * @param props.children - 折叠内容（中间 text、工具行、思考过程）
 */
function TaskCompleteSection({ streaming, lang, hasContent, children }: { streaming: boolean; lang: UiLanguage; hasContent: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(streaming);
  // 用户是否手动操作过（展开/折叠）：手动操作后自动状态变化不再覆盖
  const interactedRef = useRef(false);
  // React 官方 "adjusting state during render" 模式：prev 值用 state 存储
  const [prevStreaming, setPrevStreaming] = useState(streaming);

  // streaming 变化（流式开始/完成）时自动同步展开状态；用户手动操作过则不覆盖
  if (streaming !== prevStreaming) {
    setPrevStreaming(streaming);
    if (!interactedRef.current) setOpen(streaming);
  }

  const handleToggle = () => {
    interactedRef.current = true;
    setOpen(!open);
  };

  return (
    <div className="my-2">
      {/* 三级标题：与最终回复 markdown 渲染的 h3（.prose h3 = 1.125em/700/主色）保持一致 */}
      <h3 className="text-lg font-bold text-content-primary">
        <button
          onClick={handleToggle}
          className="flex items-center gap-2 transition-colors py-1.5 cursor-pointer"
        >
          <span>{t(lang, streaming ? 'task_in_progress' : 'task_complete')}</span>
          <svg
            className={`w-4 h-4 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4.5 2.5L8 6L4.5 9.5" />
          </svg>
        </button>
      </h3>
      {/* 标题下方的分隔直线 */}
      <div className="border-t border-border-light" />
      {open && hasContent && <div className="mt-1.5">{children}</div>}
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
  // 用户是否上滑过（查看历史）：true 时流式增长不打扰
  const userScrolledUpRef = useRef(false);
  // 程序滚动标记：auto-scroll 赋值 scrollTop 后派生的 scroll 事件用此忽略，
  // 避免被当作"用户滚动"误判（赋值后 scrollTop 在底部，位置判定也兜底）
  const programmaticScrollRef = useRef(false);

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

  /** 检查滚动容器是否在底部附近（按钮显示用：离开底部较远时显示"回到底部"） */
  const isNearBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return true;
    const max = el.scrollHeight - el.clientHeight;
    return el.scrollTop >= max - BOTTOM_THRESHOLD_PX;
  }, []);

  /** 滚动事件处理：程序滚动（auto-scroll 赋值）派生的 scroll 事件忽略；
   *  用户滚动则更新"是否上滑"标志——滚回底部附近自动恢复跟随 */
  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) {
      programmaticScrollRef.current = false;
      return;
    }
    const nearBottom = isNearBottom();
    userScrolledUpRef.current = !nearBottom;
    setShowScrollDown(!nearBottom && scrollRef.current ? scrollRef.current.scrollHeight - scrollRef.current.clientHeight > 200 : false);
  }, [isNearBottom]);

  /** 一键回到底部 */
  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    userScrolledUpRef.current = false;
    setShowScrollDown(false);
  }, []);

  // 内容变化时自动滚动到底部：用户未上滑时无条件跟随（流式大段增量也能跟上）；
  // 用户上滑过则仅在滚回底部附近（< FOLLOW_THRESHOLD_PX）时恢复跟随。
  // 程序赋值后派生的 scroll 事件用 programmaticScrollRef 忽略；即使被误判，
  // 位置兜底保证用户滚回底部后能恢复，不会永久卡住。
  // 卡片弹出时强制回到底部：模态卡片是交互元素，即使此前用户上滑查看过历史，
  // 也必须保证卡片可见，否则用户看不到问题与提交按钮
  const prevModalRef = useRef<boolean | null>(null);
  useEffect(() => {
    // 先更新状态机再取容器：restore 分支（无滚动容器）下 ref 保持最新，
    // 避免恢复会话后首个 modal 的"出现"检测被陈旧值干扰
    const modalAppeared = prevModalRef.current === false && !!modal;
    prevModalRef.current = !!modal;
    const el = scrollRef.current;
    if (!el) return;
    if (modalAppeared) {
      userScrolledUpRef.current = false;
      const prevTop = el.scrollTop;
      el.scrollTop = el.scrollHeight;
      if (el.scrollTop !== prevTop) programmaticScrollRef.current = true;
      setShowScrollDown(false);
      return;
    }
    if (userScrolledUpRef.current) {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distance > FOLLOW_THRESHOLD_PX) return; // 用户上滑中，不打扰
      userScrolledUpRef.current = false; // 滚回底部附近，恢复跟随
    }
    const prevTop = el.scrollTop;
    el.scrollTop = el.scrollHeight;
    if (el.scrollTop !== prevTop) programmaticScrollRef.current = true;
    setShowScrollDown(false); // 跟随到底后隐藏"回到底部"按钮
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
    <div className="flex-1 min-h-0 overflow-y-auto relative" ref={scrollRef} onScroll={handleScroll}>
      {!connected && !hasContent && (
        <div className="flex items-center justify-center h-full text-content-disabled text-sm font-medium">
          {t(lang, 'connecting')}
        </div>
      )}
      {connected && !hasContent && (
        <WelcomeScreen lang={lang} />
      )}

      {(hasContent || busy) && (
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
          // 轮是否仍在流式：busy=true 与 user 消息（transcript_item）存在网络往返
          // 窗口期——若仅按 busy && isLastTurn 判定，窗口期内旧轮会被误判为流式轮，
          // 上一条回复的思考过程闪开又折叠。"轮已完成"判定：最后一条是 assistant
          // 完成消息（tool_started 时 pushStatic 的中间 assistant 消息伴随
          // pendingToolCalls 非空，排除）。
          const turnFinished =
            turn.length > 0 &&
            turn[turn.length - 1]!.role === 'assistant' &&
            pendingToolCalls.length === 0;
          const turnStreaming = busy && isLastTurn && !turnFinished;
          const { userItems, thinkingItems, finalAssistant } = splitTurnItems(turn, turnStreaming);
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
              {/* 二级折叠："任务完成"大标题区——折叠最终回复之前的所有内容
                  （中间 text、工具行、思考过程、最终回复的思考过程）；
                  流式阶段（turnStreaming）强制渲染显示"任务进行中"标题
                  （即使中间内容尚未推入），完成后自动折叠 */}
              {(turnStreaming || thinkingItems.length > 0 || finalAssistant?.reasoning?.trim()) && (
                <TaskCompleteSection
                  streaming={turnStreaming}
                  lang={lang}
                  hasContent={thinkingItems.length > 0 || !!finalAssistant?.reasoning?.trim()}
                >
                  {thinkingItems.map((item, msgIdx) => (
                    <MessageBubble
                      key={`t-${turnIdx}-${msgIdx}`}
                      item={item}
                      toolInputMap={toolInputMap}
                      lang={lang}
                      showActions={false}
                    />
                  ))}
                  {finalAssistant?.reasoning?.trim() && <ThinkingBlock text={finalAssistant.reasoning} lang={lang} />}
                </TaskCompleteSection>
              )}
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
            <StreamingBuffer text={assistantBuffer} reasoning={streamingReasoning} lang={lang} />
          </div>
        )}
        {modal?.kind === 'permission' && (
          <PermissionCard modal={modal} lang={lang} onRespond={onPermissionResponse} />
        )}
        {/* key 绑定 request_id：新模态框（新问题）到来时整体重置 QuestionCard 内部状态 */}
        {modal?.kind === 'question' && (
          <QuestionCard key={modal?.request_id ? String(modal.request_id) : 'q'} modal={modal} lang={lang} onRespond={onQuestionResponse} />
        )}
      </div>
      )}

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
