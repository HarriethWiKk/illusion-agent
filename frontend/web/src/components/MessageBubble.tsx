import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface MessageBubbleProps {
  item: TranscriptItem;
}

export default function MessageBubble({ item }: MessageBubbleProps) {
  if (item.role === 'user') {
    return (
      <div className="flex justify-end py-1.5">
        <div className="max-w-[min(82%,64ch)] bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5] rounded-[6px] px-3 py-2 text-sm text-content-primary whitespace-pre-wrap break-words select-text">
          {item.text}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    return (
      <div className="py-1.5">
        {item.reasoning && <ThinkingBlock text={item.reasoning} />}
        <div className="text-content-primary text-sm prose max-w-full select-text">
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
        <div className={`mt-1 ml-3.5 p-2.5 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto rounded-[6px] select-text ${isError ? 'text-danger bg-red-50 border border-red-200' : 'text-content-primary bg-[rgba(0,0,0,0.031)] border border-[#e5e5e5]'}`}>
          {text}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  if (!text?.trim()) return null;
  return (
    <div className="text-sm text-content-secondary whitespace-pre-wrap leading-relaxed select-text mb-3 opacity-75">
      {text}
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

export function StreamingBuffer({ text, reasoning }: { text: string; reasoning?: string }) {
  const hasReasoning = reasoning && reasoning.trim();
  const hasText = text && text.trim();

  return (
    <div className="py-1.5">
      {hasReasoning && (
        <div className="text-sm text-content-secondary whitespace-pre-wrap leading-relaxed select-text mb-3 opacity-75">
          {reasoning}
          {!hasText && <span className="inline-block w-0.5 h-4 bg-content-secondary animate-blink ml-0.5 align-middle" />}
        </div>
      )}
      {hasText && (
        <div className="text-content-primary text-sm prose max-w-full select-text">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight, rehypeRaw]}>
            {text}
          </ReactMarkdown>
          <span className="inline-block w-0.5 h-4 bg-primary animate-blink align-middle" />
        </div>
      )}
    </div>
  );
}
