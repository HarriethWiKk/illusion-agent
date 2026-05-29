import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import { t, type UiLanguage } from '../i18n';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface MessageBubbleProps {
  item: TranscriptItem;
  lang?: UiLanguage;
}

export default function MessageBubble({ item, lang }: MessageBubbleProps) {
  if (item.role === 'user') {
    return (
      <div className="flex justify-end py-1.5">
        <div className="max-w-[min(82%,64ch)] bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5] rounded-[6px] px-3 py-2 text-sm text-content-primary whitespace-pre-wrap break-words">
          {item.text}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    return (
      <div className="py-1.5">
        {item.reasoning && <ThinkingBlock text={item.reasoning} defaultOpen={true} label={lang ? t(lang, 'thinking_process') : undefined} />}
        <div className="text-content-primary text-sm prose max-w-full">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight, rehypeRaw]}>
            {item.text}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (item.role === 'tool_result') {
    return <ToolResultBubble name={item.tool_name || 'tool'} text={item.text} isError={item.is_error} />;
  }

  if (item.role === 'tool') {
    return null;
  }

  return (
    <div className="py-1.5 text-xs text-content-disabled italic">
      {item.text}
    </div>
  );
}

function ToolResultBubble({ name, text, isError }: { name: string; text: string; isError?: boolean }) {
  const [open, setOpen] = useState(false);
  const firstLine = text ? text.split('\n')[0] || '' : '';
  const summary = firstLine.length > 60 ? firstLine.slice(0, 60) + '...' : firstLine;

  return (
    <div className="py-1.5">
      <button
        onClick={() => text && setOpen(!open)}
        className={`flex items-center gap-2 text-sm transition-colors cursor-pointer ${text ? 'text-content-secondary hover:text-content-primary' : ''}`}
      >
        <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${isError ? 'bg-danger' : 'bg-primary'}`} />
        <span className={`font-medium font-mono ${isError ? 'text-danger' : 'text-content-primary'}`}>{name}</span>
        {!open && summary && <span className="text-xs text-content-disabled truncate">（{summary}）</span>}
        {isError && <span className="text-xs text-danger font-medium">ERROR</span>}
      </button>
      {open && text && (
        <div className={`mt-1 ml-3.5 p-2.5 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto rounded-[6px] ${isError ? 'text-danger bg-red-50 border border-red-200' : 'text-content-primary bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5]'}`}>
          {text}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ text, defaultOpen = false, label }: { text: string; defaultOpen?: boolean; label?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const preview = text.length > 100 ? text.slice(0, 100) + '...' : text;

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-content-secondary hover:text-content-primary transition-colors cursor-pointer w-full"
      >
        <span className="inline-block w-2 h-2 rounded-full bg-primary shrink-0" />
        <span className="font-medium">{label || '思考过程'}</span>
        {!open && <span className="text-content-disabled truncate flex-1 text-left">{preview}</span>}
        <span className={`transform transition-transform shrink-0 ${open ? 'rotate-90' : ''}`}>▸</span>
      </button>
      {open && (
        <div className="mt-2 ml-3.5 p-3 bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5] text-sm text-content-primary whitespace-pre-wrap rounded-[6px] leading-relaxed">
          {text}
        </div>
      )}
    </div>
  );
}

export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  const hasInput = call.tool_input && Object.keys(call.tool_input).length > 0;
  return (
    <div className="py-1.5">
      <div className="flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse-scale shrink-0" />
        <span className="text-sm font-medium font-mono text-content-primary">{call.tool_name}</span>
      </div>
      {hasInput && (
        <div className="ml-4 mt-1.5 space-y-0.5">
          {Object.entries(call.tool_input!).map(([key, val]) => (
            <div key={key} className="flex items-start gap-2 text-xs">
              <span className="text-content-disabled font-mono shrink-0">{key}:</span>
              <span className="text-content-secondary truncate">{formatToolValue(val)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatToolValue(val: unknown): string {
  if (val === null || val === undefined) return '-';
  if (typeof val === 'string') return val.length > 120 ? val.slice(0, 120) + '...' : val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  const s = JSON.stringify(val);
  return s.length > 120 ? s.slice(0, 120) + '...' : s;
}

export function StreamingBuffer({ text, reasoning, lang }: { text: string; reasoning?: string; lang?: UiLanguage }) {
  const hasReasoning = reasoning && reasoning.trim();
  const hasText = text && text.trim();

  return (
    <div className="py-1.5">
      {hasReasoning && (
        <div className={hasText ? 'mb-3' : ''}>
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse-scale shrink-0" />
            <span className="text-xs font-medium text-content-secondary">{lang ? t(lang, 'thinking_process') : '思考过程'}</span>
          </div>
          <div className="ml-3.5 p-3 bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5] text-xs text-content-primary whitespace-pre-wrap rounded-[6px] leading-relaxed">
            {reasoning}
            {!hasText && <span className="inline-block w-0.5 h-4 bg-primary animate-pulse ml-0.5 align-middle" />}
          </div>
        </div>
      )}
      {hasText && (
        <div className="text-content-primary text-sm prose max-w-full">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight, rehypeRaw]}>
            {text}
          </ReactMarkdown>
          <span className="inline-block w-0.5 h-4 bg-primary animate-blink align-middle" />
        </div>
      )}
    </div>
  );
}
