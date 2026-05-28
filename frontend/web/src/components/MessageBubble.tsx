import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
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
      <div className="flex justify-end py-2">
        <div className="max-w-[75%] bg-primary text-white rounded-2xl rounded-br-md px-5 py-3.5 text-base shadow-soft">
          {item.text}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    return (
      <div className="py-2">
        <div className="bg-white rounded-2xl px-6 py-5 shadow-card border border-border-light">
          {item.reasoning && <ThinkingBlock text={item.reasoning} defaultOpen={true} label={lang ? t(lang, 'thinking_process') : undefined} />}
          <div className="text-content-primary text-base prose max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {item.text}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    );
  }

  if (item.role === 'tool_result') {
    const isError = item.is_error;
    return (
      <div className="py-1.5">
        <div className={`bg-white rounded-xl shadow-card border overflow-hidden ${isError ? 'border-red-300' : 'border-border-light'}`}>
          {/* 工具头部 */}
          <ToolHeader
            name={item.tool_name || 'tool'}
            input={item.tool_input}
            isError={isError}
          />
          {/* 工具输出 */}
          <ToolOutput text={item.text} isError={isError} />
        </div>
      </div>
    );
  }

  if (item.role === 'tool') {
    return null;
  }

  return (
    <div className="py-1.5 text-sm text-content-disabled italic px-4">
      {item.text}
    </div>
  );
}

function ToolHeader({ name, input, isError }: { name: string; input?: Record<string, unknown>; isError?: boolean }) {
  const hasInput = input && Object.keys(input).length > 0;

  return (
    <div className="px-5 py-3 bg-surface-card-alt border-b border-border-light">
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${isError ? 'bg-danger' : 'bg-primary'}`} />
        <div className={`text-sm font-semibold font-mono ${isError ? 'text-danger' : 'text-content-primary'}`}>{name}</div>
        {isError && <span className="text-xs text-danger font-medium ml-auto px-2 py-0.5 bg-red-50 rounded">ERROR</span>}
      </div>
      {hasInput && (
        <div className="mt-2 space-y-1">
          {Object.entries(input).map(([key, val]) => (
            <div key={key} className="flex items-start gap-2 text-xs">
              <span className="text-content-secondary font-mono shrink-0">{key}:</span>
              <span className="text-content-primary font-mono break-all">{formatValue(val)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatValue(val: unknown): string {
  if (typeof val === 'string') return val.length > 200 ? val.slice(0, 200) + '...' : val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  const json = JSON.stringify(val);
  return json.length > 200 ? json.slice(0, 200) + '...' : json;
}

function ToolOutput({ text, isError }: { text: string; isError?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-2.5 flex items-center gap-2 text-sm text-content-secondary hover:text-content-primary hover:bg-surface-hover transition-colors cursor-pointer"
      >
        <span className={`transform transition-transform text-xs ${open ? 'rotate-90' : ''}`}>▸</span>
        <span className="font-medium">输出</span>
        {!open && <span className="text-content-disabled truncate ml-1 text-xs">{text.slice(0, 60)}{text.length > 60 ? '...' : ''}</span>}
      </button>
      {open && (
        <div className={`px-5 pb-3 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto ${isError ? 'text-danger bg-red-50' : 'text-content-primary bg-surface-card-alt'} mx-3 mb-3 rounded-lg p-3`}>
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
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm text-content-secondary hover:text-content-primary transition-colors cursor-pointer group w-full"
      >
        <span className="inline-block w-2 h-2 rounded-full bg-secondary group-hover:bg-secondary-hover transition-colors" />
        <span className="font-medium">{label || '思考过程'}</span>
        {!open && <span className="text-content-disabled truncate flex-1 text-left text-xs">{preview}</span>}
        <span className={`transform transition-transform text-xs ${open ? 'rotate-90' : ''}`}>▸</span>
      </button>
      {open && (
        <div className="mt-3 p-4 bg-primary-light text-sm text-content-primary whitespace-pre-wrap border border-primary/20 rounded-xl max-h-56 overflow-y-auto leading-relaxed">
          {text}
        </div>
      )}
    </div>
  );
}

export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  return (
    <div className="py-1.5">
      <div className="bg-white rounded-xl px-5 py-3 border border-border-light shadow-card">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />
          <span className="text-sm font-semibold font-mono text-content-primary">{call.tool_name}</span>
        </div>
        {call.tool_input && Object.keys(call.tool_input).length > 0 && (
          <div className="mt-2 p-2.5 bg-surface-card-alt text-xs font-mono text-content-secondary whitespace-pre-wrap max-h-32 overflow-y-auto rounded border border-border-light">
            {JSON.stringify(call.tool_input, null, 2)}
          </div>
        )}
      </div>
    </div>
  );
}

export function StreamingBuffer({ text, reasoning, lang }: { text: string; reasoning?: string; lang?: UiLanguage }) {
  const hasReasoning = reasoning && reasoning.trim();
  const hasText = text && text.trim();

  return (
    <div className="py-2">
      <div className="bg-white rounded-2xl px-6 py-5 shadow-card border border-border-light">
        {hasReasoning && (
          <div className={hasText ? 'mb-4' : ''}>
            <div className="flex items-center gap-2 text-sm text-content-secondary mb-2">
              <span className="inline-block w-2 h-2 rounded-full bg-secondary animate-pulse" />
              <span className="font-medium text-xs">{lang ? t(lang, 'thinking_process') : '思考过程'}</span>
            </div>
            <div className="p-3 bg-primary-light text-xs text-content-primary whitespace-pre-wrap border border-primary/20 rounded-xl max-h-48 overflow-y-auto leading-relaxed">
              {reasoning}
              {!hasText && <span className="inline-block w-1 h-3 bg-primary animate-pulse ml-0.5 align-middle" />}
            </div>
          </div>
        )}
        {hasText && (
          <div className="text-content-primary text-base prose max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
              {text}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
