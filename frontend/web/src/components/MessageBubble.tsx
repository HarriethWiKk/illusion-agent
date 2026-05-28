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
        <div className="bg-white/90 backdrop-blur-sm rounded-2xl px-6 py-5 shadow-soft border border-sand-200/60">
          {item.reasoning && <ThinkingBlock text={item.reasoning} defaultOpen={true} label={lang ? t(lang, 'thinking_process') : undefined} />}
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
        <div className={`bg-white/90 backdrop-blur-sm rounded-xl shadow-soft border overflow-hidden ${isError ? 'border-red-200/60' : 'border-sand-200/60'}`}>
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
  const hasInput = input && Object.keys(input).length > 0;

  return (
    <div className="px-6 py-3">
      <div className="flex items-center gap-2.5">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${isError ? 'bg-red-400' : 'bg-gradient-to-br from-cream-400 to-khaki-400'}`} />
        <div className={`text-sm font-medium ${isError ? 'text-red-600' : 'text-khaki-700'}`}>{name}</div>
        {isError && <span className="text-[10px] text-red-500 font-medium ml-auto">ERROR</span>}
      </div>
      {hasInput && (
        <div className="mt-2 p-3 bg-cream-100/60 rounded-lg text-xs font-mono text-khaki-600 whitespace-pre-wrap max-h-40 overflow-y-auto border border-sand-200/40">
          {JSON.stringify(input, null, 2)}
        </div>
      )}
    </div>
  );
}

function ToolOutput({ text, isError }: { text: string; isError?: boolean }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;

  return (
    <div className="border-t border-sand-200/40">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-6 py-2 flex items-center gap-2 text-xs text-khaki-500 hover:text-khaki-700 transition-colors duration-200 cursor-pointer"
      >
        <span className={`transform transition-transform duration-200 text-[10px] ${open ? 'rotate-90' : ''}`}>▸</span>
        <span className="font-medium">输出</span>
        {!open && <span className="text-khaki-400 truncate ml-1">{text.slice(0, 60)}{text.length > 60 ? '...' : ''}</span>}
      </button>
      {open && (
        <div className={`px-6 pb-3 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto ${isError ? 'text-red-600' : 'text-khaki-600'}`}>
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

export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  return (
    <div className="py-1.5">
      <div className="bg-white/90 backdrop-blur-sm rounded-xl px-4 py-3 border border-sand-200/60 shadow-soft">
        <div className="flex items-center gap-2.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-gradient-to-br from-cream-400 to-khaki-400 animate-pulse" />
          <span className="text-sm font-medium text-khaki-700">{call.tool_name}</span>
        </div>
        {call.tool_input && Object.keys(call.tool_input).length > 0 && (
          <div className="mt-2 p-2.5 bg-cream-100/60 rounded-lg text-xs font-mono text-khaki-500 whitespace-pre-wrap max-h-32 overflow-y-auto border border-sand-200/40">
            {JSON.stringify(call.tool_input, null, 2)}
          </div>
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
            <div className="flex items-center gap-2 text-sm text-khaki-500 mb-2">
              <span className="inline-block w-2 h-2 rounded-full bg-khaki-400 animate-pulse" />
              <span className="font-medium text-xs">{lang ? t(lang, 'thinking_process') : '思考过程'}</span>
            </div>
            <div className="p-3 bg-cream-100/60 rounded-lg text-xs text-khaki-600 whitespace-pre-wrap border border-sand-200/40 max-h-48 overflow-y-auto leading-relaxed">
              {reasoning}
              <span className="inline-block w-1 h-3 bg-khaki-300 animate-pulse ml-0.5 align-middle" />
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
