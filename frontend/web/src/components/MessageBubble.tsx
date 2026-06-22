/**
 * @fileoverview 消息气泡组件
 *
 * Web 前端的消息显示组件，支持：
 * - 用户消息（右对齐）
 * - 助手回复（左对齐，支持 Markdown 渲染）
 * - 工具调用结果（可展开/折叠）
 * - 待处理工具调用（带脉冲动画）
 * - 流式回复缓冲区
 *
 * @module MessageBubble
 */

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkSuperscript from '../remarkSuperscript';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

/**
 * MessageBubble 组件属性接口
 */
interface MessageBubbleProps {
  /** 转录项 */
  item: TranscriptItem;
  /** 工具输入映射（用于显示工具调用参数） */
  toolInputMap?: Map<string, Record<string, unknown>>;
}

/**
 * 消息气泡组件
 *
 * 根据消息角色类型渲染不同的消息样式。
 *
 * @param props - 组件属性
 * @returns 返回消息气泡的 JSX 元素
 */
export default function MessageBubble({ item, toolInputMap }: MessageBubbleProps) {
  if (item.role === 'user') {
    return (
      <div className="flex justify-end py-1.5">
        <div className="max-w-[min(82%,64ch)] bg-surface-card-alt border border-border-light rounded-[6px] px-3 py-2 text-sm text-content-primary whitespace-pre-wrap break-words select-text">
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
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]}>
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

/**
 * 工具结果气泡组件
 *
 * 显示工具执行结果，支持展开/折叠查看详情。
 *
 * @param props - 组件属性
 * @param props.name - 工具名称
 * @param props.text - 结果文本
 * @param props.isError - 是否为错误结果
 * @param props.toolInput - 工具输入参数
 */
function ToolResultBubble({ name, text, isError, toolInput }: { name: string; text: string; isError?: boolean; toolInput?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const summary = summarizeInput(name, toolInput, name);

  return (
    <div className="py-1.5">
      <button
        onClick={() => text && setOpen(!open)}
        className={`flex items-start gap-2 text-sm transition-colors cursor-pointer text-left ${text ? 'text-content-secondary hover:text-content-primary' : ''}`}
      >
        <span className={`inline-block w-2 h-2 rounded-full shrink-0 mt-1.5 ${isError ? 'bg-danger' : 'bg-primary'}`} />
        <span>
          <span className={`font-medium font-mono ${isError ? 'text-danger' : 'text-content-primary'}`}>{name}</span>
          {!open && summary && <span className={`text-xs ${isError ? 'text-danger' : 'text-content-disabled'}`}>（{summary}）</span>}
          {isError && <span className="text-xs text-danger font-medium"> ERROR</span>}
        </span>
      </button>
      {open && text && (
        <div className={`mt-1 ml-3.5 p-2.5 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto rounded-[6px] select-text ${isError ? 'text-danger bg-danger/5 border border-danger/20' : 'text-content-primary bg-surface-card-alt border border-border-light'}`}>
          {text}
        </div>
      )}
    </div>
  );
}

/**
 * 思考过程块组件
 *
 * 显示助手的思考/推理过程。
 *
 * @param props - 组件属性
 * @param props.text - 思考过程文本
 */
function ThinkingBlock({ text }: { text: string }) {
  if (!text?.trim()) return null;
  return (
    <div className="text-sm text-content-secondary whitespace-pre-wrap leading-relaxed select-text mb-3 opacity-75">
      {text}
    </div>
  );
}

/**
 * 待处理工具调用气泡组件
 *
 * 显示正在执行的工具调用，带有脉冲动画效果。
 *
 * @param props - 组件属性
 * @param props.call - 待处理的工具调用信息
 */
export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  const summary = summarizeInput(call.tool_name, call.tool_input, call.tool_name);
  return (
    <div className="py-1.5 flex items-start gap-2">
      <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse-scale shrink-0 mt-1.5" />
      <span className="text-sm">
        <span className="font-medium font-mono text-content-primary">{call.tool_name}</span>
        {summary && <span className="text-xs text-content-disabled">（{summary}）</span>}
      </span>
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

/**
 * 流式缓冲区组件
 *
 * 显示正在流式接收的助手回复，包括思考过程和正文。
 *
 * @param props - 组件属性
 * @param props.text - 正文文本
 * @param props.reasoning - 思考过程文本（可选）
 */
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
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]}>
            {text}
          </ReactMarkdown>
          <span className="inline-block w-0.5 h-4 bg-primary animate-blink align-middle" />
        </div>
      )}
    </div>
  );
}
