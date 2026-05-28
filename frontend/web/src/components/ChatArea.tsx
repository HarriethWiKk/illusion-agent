import { useEffect, useRef } from 'react';
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

  return (
    <div className="flex-1 overflow-y-auto bg-gradient-to-b from-cream-50/30 via-transparent to-sand-50/30">
      {!connected && !hasContent && (
        <div className="flex items-center justify-center h-full text-khaki-400 text-base font-medium animate-pulse">
          {t(lang, 'connecting')}
        </div>
      )}
      {connected && !hasContent && (
        <WelcomeScreen lang={lang} />
      )}

      <div className="max-w-[900px] mx-auto py-6 px-4">
        {staticItems.map((item, idx) => (
          <div key={idx} className="animate-slide-up" style={{ animationDelay: `${idx * 50}ms` }}>
            <MessageBubble item={item} lang={lang} />
          </div>
        ))}
        {pendingToolCalls.map((call) => (
          <div key={call.tool_use_id} className="animate-slide-up">
            <PendingToolBubble call={call} />
          </div>
        ))}
        {busy && (assistantBuffer || streamingReasoning) && (
          <StreamingBuffer text={assistantBuffer} reasoning={streamingReasoning} lang={lang} />
        )}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
