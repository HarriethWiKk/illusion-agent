import { useEffect, useMemo, useRef } from 'react';
import { t, type UiLanguage } from '../i18n';
import MessageBubble, { PendingToolBubble, StreamingBuffer } from './MessageBubble';
import WelcomeScreen from './WelcomeScreen';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface ChatAreaProps {
  lang: UiLanguage;
  staticItems: TranscriptItem[];
  assistantBuffer: string;
  streamingReasoning: string;
  pendingToolCalls: PendingToolCall[];
  busy: boolean;
  connected: boolean;
}

export default function ChatArea({
  lang, staticItems, assistantBuffer, streamingReasoning, pendingToolCalls, busy, connected,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [staticItems, assistantBuffer, streamingReasoning, pendingToolCalls]);

  const hasContent = staticItems.length > 0 || assistantBuffer || streamingReasoning || pendingToolCalls.length > 0;

  // 按用户消息分组为轮次(turn)，每轮以用户消息开头
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

  return (
    <div className="flex-1 overflow-y-auto bg-surface-main">
      {!connected && !hasContent && (
        <div className="flex items-center justify-center h-full text-content-disabled text-sm font-medium">
          {t(lang, 'connecting')}
        </div>
      )}
      {connected && !hasContent && (
        <WelcomeScreen lang={lang} />
      )}

      <div className="mx-auto px-6 md:px-10 lg:px-16 py-6">
        {turns.map((turn, turnIdx) => (
          <div key={turnIdx} className={turnIdx > 0 ? 'mt-12' : ''}>
            {turn.map((item, msgIdx) => (
              <MessageBubble key={`${turnIdx}-${msgIdx}`} item={item} lang={lang} />
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
        {busy && (assistantBuffer || streamingReasoning) && (
          <div className={turns.length > 0 ? 'mt-4' : ''}>
            <StreamingBuffer text={assistantBuffer} reasoning={streamingReasoning} lang={lang} />
          </div>
        )}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
