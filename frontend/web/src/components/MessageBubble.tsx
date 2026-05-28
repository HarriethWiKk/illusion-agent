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
        <div className="max-w-[75%] bg-gradient-to-br from-cream-200 to-sand-200 text-khaki-800 rounded-2xl rounded-br-md px-5 py-3.5 text-base shadow-soft border border-sand-300/50 hover:shadow-warm transition-shadow duration-300">
          {item.text}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    return (
      <div className="py-2">
        <div className="bg-white/90 backdrop-blur-sm rounded-2xl px-6 py-5 shadow-soft border border-sand-200/60 hover:shadow-warm transition-shadow duration-300">
          {item.reasoning && <ThinkingBlock text={item.reasoning} defaultOpen={false} label={lang ? t(lang, 'thinking_process') : undefined} />}
          <div className="text-khaki-800 text-base prose prose-stone max-w-none">
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
        <div className={`rounded-xl overflow-hidden shadow-soft border ${isError ? 'border-red-200/60 bg-red-50/40' : 'border-sand-200/60 bg-white/90 backdrop-blur-sm'} hover:shadow-warm transition-shadow duration-300`}>
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
    <div className="py-1.5 text-sm text-khaki-400 italic px-4">
      {item.text}
    </div>
  );
}

function ToolHeader({ name, input, isError }: { name: string; input?: Record<string, unknown>; isError?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const hasInput = input && Object.keys(input).length > 0;

  return (
    <div className="flex items-center gap-3 px-4 py-3">
      {/* 左侧色条 */}
      <div className={`w-1 h-8 rounded-full ${isError ? 'bg-red-400' : 'bg-gradient-to-b from-cream-400 to-khaki-400'}`} />
      {/* 工具图标 */}
      <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-sm ${isError ? 'bg-red-100 text-red-500' : 'bg-gradient-to-br from-cream-200 to-sand-200 text-khaki-600'}`}>
        {isError ? '!' : '⚙'}
      </div>
      {/* 工具名和参数 */}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-khaki-700 font-mono">{name}</div>
        {hasInput && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-khaki-400 hover:text-khaki-600 cursor-pointer mt-1 flex items-center gap-1 transition-colors duration-200"
          >
            <span className={`transform transition-transform duration-200 text-[10px] ${expanded ? 'rotate-90' : ''}`}>▸</span>
            {formatToolInput(input)}
          </button>
        )}
      </div>
      {expanded && hasInput && (
        <div className="absolute top-full left-0 right-0 mt-0 z-10 animate-slide-down">
          <div className="mx-4 mb-2 bg-cream-100/95 backdrop-blur-sm border border-sand-200/80 rounded-xl p-3 text-xs font-mono text-khaki-600 whitespace-pre-wrap max-h-40 overflow-y-auto shadow-warm">
            {JSON.stringify(input, null, 2)}
          </div>
        </div>
      )}
    </div>
  );
}

function ToolOutput({ text, isError }: { text: string; isError?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div className="border-t border-sand-200/60">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-2.5 flex items-center gap-2 text-xs text-khaki-400 hover:text-khaki-600 hover:bg-cream-100/50 transition-all duration-200 cursor-pointer"
      >
        <span className={`transform transition-transform duration-200 text-[10px] ${open ? 'rotate-90' : ''}`}>▸</span>
        <span>输出</span>
        {!open && <span className="text-khaki-300 truncate">{text.slice(0, 60)}{text.length > 60 ? '...' : ''}</span>}
      </button>
      {open && (
        <div className={`px-4 pb-3 whitespace-pre-wrap font-mono text-sm leading-relaxed max-h-60 overflow-y-auto animate-fade-in ${isError ? 'text-red-600' : 'text-khaki-600'}`}>
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
        className="flex items-center gap-2.5 text-sm text-khaki-400 hover:text-khaki-600 transition-colors duration-200 cursor-pointer group w-full"
      >
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-cream-400 to-khaki-400 group-hover:from-cream-500 group-hover:to-khaki-500 transition-all duration-200 shadow-sm" />
        <span className="font-medium">{label || '思考过程'}</span>
        {!open && <span className="text-khaki-300 truncate flex-1 text-left text-xs">{preview}</span>}
        <span className={`transform transition-transform duration-200 text-xs ${open ? 'rotate-90' : ''}`}>▸</span>
      </button>
      {open && (
        <div className="mt-3 p-4 bg-gradient-to-br from-cream-100/80 to-sand-100/80 rounded-xl text-sm text-khaki-600 whitespace-pre-wrap border border-sand-200/60 max-h-56 overflow-y-auto leading-relaxed animate-slide-down">
          {text}
        </div>
      )}
    </div>
  );
}

function formatToolInput(input: Record<string, unknown>): string {
  const entries = Object.entries(input);
  if (entries.length === 0) return '';
  const first = entries[0];
  if (!first) return '';
  const [key, val] = first;
  const valStr = typeof val === 'string' ? val : JSON.stringify(val);
  const truncated = valStr.length > 80 ? valStr.slice(0, 80) + '...' : valStr;
  const more = entries.length > 1 ? ` +${entries.length - 1}` : '';
  return `${key}=${truncated}${more}`;
}

export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  return (
    <div className="py-1.5">
      <div className="flex items-center gap-3 text-sm bg-white/90 backdrop-blur-sm rounded-xl px-4 py-3 border border-sand-200/60 shadow-soft animate-pulse-warm">
        <span className="inline-block w-3 h-3 rounded-full bg-gradient-to-br from-cream-400 to-khaki-400 animate-pulse shadow-[0_0_8px_rgba(184,134,11,0.3)]" />
        <span className="font-mono font-medium text-khaki-700">{call.tool_name}</span>
        {call.tool_input && Object.keys(call.tool_input).length > 0 && (
          <span className="text-khaki-400 truncate max-w-[400px] text-xs">
            {formatToolInput(call.tool_input)}
          </span>
        )}
      </div>
    </div>
  );
}

export function StreamingBuffer({ text, reasoning, lang }: { text: string; reasoning?: string; lang?: UiLanguage }) {
  return (
    <div className="py-2">
      <div className="bg-white/90 backdrop-blur-sm rounded-2xl px-6 py-5 shadow-soft border border-sand-200/60">
        {reasoning && reasoning.trim() && (
          <div className="mb-4">
            <div className="flex items-center gap-2.5 text-sm text-khaki-500 mb-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-cream-400 to-khaki-400 animate-pulse shadow-[0_0_8px_rgba(184,134,11,0.3)]" />
              <span className="font-medium">{lang ? t(lang, 'thinking_process') : '思考过程'}</span>
            </div>
            <div className="p-4 bg-gradient-to-br from-cream-100/80 to-sand-100/80 rounded-xl text-sm text-khaki-600 whitespace-pre-wrap border border-sand-200/60 max-h-56 overflow-y-auto leading-relaxed">
              {reasoning}
              <span className="inline-block w-1.5 h-4 bg-khaki-300 animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}
        <div className="text-khaki-800 text-base prose prose-stone max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {text || '▍'}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
