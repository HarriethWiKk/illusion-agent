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

import { useEffect, useMemo, useRef } from 'react';
import { t, type UiLanguage } from '../i18n';
import MessageBubble, { PendingToolBubble, StreamingBuffer } from './MessageBubble';
import WelcomeScreen from './WelcomeScreen';
import { PermissionCard, QuestionCard } from './ModalCard';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

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
  modal, onPermissionResponse, onQuestionResponse, restoringSessionId,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [staticItems, assistantBuffer, streamingReasoning, pendingToolCalls, modal]);

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

  // tool_use_id → tool_input 映射，用于 tool_result 摘要显示
  const toolInputMap = useMemo(() => buildToolInputMap(staticItems), [staticItems]);

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
    <div className="flex-1 overflow-y-auto">
      {!connected && !hasContent && (
        <div className="flex items-center justify-center h-full text-content-disabled text-sm font-medium">
          {t(lang, 'connecting')}
        </div>
      )}
      {connected && !hasContent && (
        <WelcomeScreen lang={lang} />
      )}

      <div className="mx-auto max-w-5xl px-6 md:px-10 lg:px-16 py-6">
        {turns.map((turn, turnIdx) => (
          <div key={turnIdx} className={turnIdx > 0 ? 'mt-12' : ''}>
            {turn.map((item, msgIdx) => (
              <MessageBubble key={`${turnIdx}-${msgIdx}`} item={item} toolInputMap={toolInputMap} />
            ))}
          </div>
        ))}
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
      <div ref={bottomRef} />
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
