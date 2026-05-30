import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

interface MessageBubbleProps {
  item: TranscriptItem;
  toolInputMap?: Map<string, Record<string, unknown>>;
}

export default function MessageBubble({ item, toolInputMap }: MessageBubbleProps) {
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
    const toolInput = (item.tool_use_id && toolInputMap?.get(item.tool_use_id)) || item.tool_input;
    return <ToolResultBubble name={item.tool_name || 'tool'} text={item.text} isError={item.is_error} toolInput={toolInput} />;
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

function ToolResultBubble({ name, text, isError, toolInput }: { name: string; text: string; isError?: boolean; toolInput?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const summary = summarizeInput(name, toolInput, name);

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
  const summary = summarizeInput(call.tool_name, call.tool_input, call.tool_name);
  return (
    <div className="py-1.5 flex items-center gap-2">
      <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse-scale shrink-0" />
      <span className="text-sm font-medium font-mono text-content-primary">{call.tool_name}</span>
      {summary && <span className="text-xs text-content-disabled truncate">（{summary}）</span>}
    </div>
  );
}

// ---- 摘要生成（与 terminal 端 summarizeInput 保持一致）----

const MAX_COMMAND_LINES = 2;
const MAX_COMMAND_CHARS = 160;

function summarizeInput(toolName: string, toolInput?: Record<string, unknown>, fallback?: string): string {
  if (!toolInput) return truncateCommand(fallback ?? '');
  const lower = toolName.toLowerCase();

  if ((lower === 'bash' || lower === 'powershell') && toolInput.command) {
    return truncateCommand(String(toolInput.command));
  }
  if ((lower === 'read' || lower === 'fileread' || lower === 'read_file') && (toolInput.path || toolInput.file_path)) {
    return String(toolInput.path ?? toolInput.file_path);
  }
  if ((lower === 'write' || lower === 'filewrite' || lower === 'write_file') && (toolInput.path || toolInput.file_path)) {
    return String(toolInput.path ?? toolInput.file_path);
  }
  if ((lower === 'edit' || lower === 'fileedit' || lower === 'edit_file') && (toolInput.path || toolInput.file_path)) {
    return String(toolInput.path ?? toolInput.file_path);
  }
  if (lower === 'grep' && toolInput.pattern) {
    return `/${String(toolInput.pattern)}/`;
  }
  if (lower === 'glob' && toolInput.pattern) {
    return String(toolInput.pattern);
  }
  if (lower === 'agent' && toolInput.description) {
    return truncateCommand(String(toolInput.description));
  }
  if (lower === 'todowrite' || lower === 'todo_write') {
    const todos = toolInput.todos;
    if (Array.isArray(todos)) {
      const total = todos.length;
      const completed = todos.filter((t: { status: string }) => t.status === 'completed').length;
      return `${completed}/${total} tasks`;
    }
  }
  if (lower === 'ask_user_question') {
    const questions = toolInput.questions;
    if (Array.isArray(questions) && questions.length > 0) {
      const q = questions[0] as Record<string, unknown>;
      return truncateCommand(String(q.question ?? ''));
    }
  }

  const entries = Object.entries(toolInput);
  if (entries.length > 0) {
    const first = entries[0];
    if (first) return truncateCommand(`${first[0]}=${String(first[1])}`);
  }
  return truncateCommand(fallback ?? '');
}

function truncateCommand(str: string): string {
  const lines = str.split('\n');
  const cleanedLines = lines.map(l => l.trim()).filter(l => l.length > 0);
  const truncatedLines = cleanedLines.length > MAX_COMMAND_LINES
    ? [...cleanedLines.slice(0, MAX_COMMAND_LINES)]
    : cleanedLines;
  let result = truncatedLines.join(' ');
  const needsCharTruncation = result.length > MAX_COMMAND_CHARS || cleanedLines.length > MAX_COMMAND_LINES;
  if (needsCharTruncation && result.length > MAX_COMMAND_CHARS) {
    result = result.slice(0, MAX_COMMAND_CHARS);
    const lastSemicolon = result.lastIndexOf(';');
    if (lastSemicolon > MAX_COMMAND_CHARS * 0.3) {
      result = result.slice(0, lastSemicolon + 1);
    } else {
      const lastSpace = result.lastIndexOf(' ');
      if (lastSpace > MAX_COMMAND_CHARS * 0.5) {
        result = result.slice(0, lastSpace);
      }
    }
  }
  if (needsCharTruncation) {
    result += '…';
  }
  return result;
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
