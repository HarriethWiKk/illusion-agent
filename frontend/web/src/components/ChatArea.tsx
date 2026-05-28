import React, { useEffect, useRef } from 'react';
import { t, type UiLanguage } from '../i18n';
import MessageBubble, { PendingToolBubble, StreamingBuffer } from './MessageBubble';
import WelcomeScreen from './WelcomeScreen';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface ChatAreaProps {
  lang: UiLanguage;
  staticItems: TranscriptItem[];
  assistantBuffer: string;
  pendingToolCalls: PendingToolCall[];
  busy: boolean;
  ready: boolean;
  connected: boolean;
}

export default function ChatArea({
  lang, staticItems, assistantBuffer, pendingToolCalls, busy, ready, connected,
}: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [staticItems, assistantBuffer, pendingToolCalls]);

  if (!connected) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        {t(lang, 'connecting')}
      </div>
    );
  }

  if (!ready && staticItems.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400">
        {t(lang, 'connecting')}
      </div>
    );
  }

  const hasContent = staticItems.length > 0 || assistantBuffer || pendingToolCalls.length > 0;

  return (
    <div className="flex-1 overflow-y-auto">
      {!hasContent && <WelcomeScreen lang={lang} />}
      {staticItems.map((item, idx) => (
        <MessageBubble key={idx} item={item} />
      ))}
      {pendingToolCalls.map((call) => (
        <PendingToolBubble key={call.tool_use_id} call={call} />
      ))}
      {busy && assistantBuffer && <StreamingBuffer text={assistantBuffer} />}
      <div ref={bottomRef} />
    </div>
  );
}
