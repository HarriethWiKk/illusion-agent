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

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkSuperscript from '../remarkSuperscript';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import { t, type UiLanguage } from '../i18n';
import type { TranscriptItem, PendingToolCall } from '../types/protocol';

/** 从 rehype-highlight 注入的 className 中提取语言名 */
function extractLanguage(props: Record<string, unknown>): string | undefined {
  const className = (props.className as string) || '';
  const match = className.match(/language-(\w+)/);
  return match?.[1];
}

/** 递归提取 React children 中的纯文本 */
function extractText(children: React.ReactNode): string {
  return React.Children.toArray(children)
    .map((c) => {
      if (typeof c === 'string') return c;
      if (typeof c === 'number') return String(c);
      if (React.isValidElement(c) && (c.props as { children?: React.ReactNode }).children) {
        return extractText((c.props as { children: React.ReactNode }).children);
      }
      return '';
    })
    .join('');
}

/** 去除代码块尾部空行，返回处理后的 children */
function trimCodeTrailingLines(children: React.ReactNode): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (!React.isValidElement(child)) return child;
    const el = child as React.ReactElement<{ children?: React.ReactNode }>;
    if (typeof el.type === 'string' && el.type === 'code') {
      const arr = React.Children.toArray(el.props.children);
      while (arr.length > 0) {
        const last = arr[arr.length - 1];
        if (typeof last === 'string' && last.trim() === '') arr.pop();
        else break;
      }
      if (arr.length > 0) {
        const last = arr[arr.length - 1];
        if (typeof last === 'string' && /\n+$/.test(last)) {
          arr[arr.length - 1] = last.replace(/\n+$/, '');
        }
      }
      return React.cloneElement(el, undefined, ...arr);
    }
    return el;
  });
}

/** 复制按钮 — opencode 风格 SVG */
function CodeCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button className={`code-copy-btn${copied ? ' copied' : ''}`} onClick={handleCopy} title="复制">
      <span className="copy-icon">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeLinecap="round">
          <path d="M6.2513 6.24935V2.91602H17.0846V13.7493H13.7513M13.7513 6.24935V17.0827H2.91797V6.24935H13.7513Z" />
        </svg>
      </span>
      <span className="copy-check">
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeLinecap="square">
          <path d="M5 11.9657L8.37838 14.7529L15 5.83398" />
        </svg>
      </span>
    </button>
  );
}

/** 自定义 <pre> —— 顶栏：语言名 + 复制按钮 */
const mdComponents = {
  pre: ({ children, ...rest }: React.ComponentPropsWithoutRef<'pre'>) => {
    const codeChild = children as React.ReactElement<{ className?: string; children?: React.ReactNode }> | undefined;
    const lang = extractLanguage((codeChild?.props as Record<string, unknown>) || {}) || 'text';
    const rawText = extractText(codeChild?.props?.children ?? children);
    return (
      <div className="code-block-wrap">
        <div className="code-block-header">
          <span className="code-lang-label">{lang}</span>
          <CodeCopyButton text={rawText} />
        </div>
        <pre {...rest}>{trimCodeTrailingLines(children)}</pre>
      </div>
    );
  },
};

/**
 * MessageBubble 组件属性接口
 */
interface MessageBubbleProps {
  /** 转录项 */
  item: TranscriptItem;
  /** 工具输入映射（用于显示工具调用参数） */
  toolInputMap?: Map<string, Record<string, unknown>>;
  /** 当前 UI 语言 */
  lang?: UiLanguage;
  /** 撤销回调（每条 user 消息均可触发，点击后弹出模式选择） */
  onRewind?: () => void;
  /** 重新生成回调（仅最终 assistant 消息显示） */
  onRegenerate?: () => void;
  /** 是否隐藏思考过程块（reasoning 由上层统一渲染时使用） */
  hideReasoning?: boolean;
  /** 是否以内联方式渲染 reasoning（无折叠开关，用于思考过程区内展示） */
  inlineReasoning?: boolean;
  /** 是否显示操作按钮（复制/撤销），思考过程内的中间消息设为 false */
  showActions?: boolean;
  /** 禁用操作按钮（busy 时禁用撤销/重新生成，复制不受影响） */
  actionsDisabled?: boolean;
}

/**
 * 消息操作按钮组 —— 复制 + 撤销 + 重新生成（hover 时显示）
 *
 * @param props.text - 待复制文本
 * @param props.lang - UI 语言
 * @param props.onRewind - 撤销回调（可选，user 消息显示）
 * @param props.onRegenerate - 重新生成回调（可选，assistant 消息显示）
 */
function MessageActions({ text, lang, onRewind, onRegenerate, disabled }: { text: string; lang: UiLanguage; onRewind?: () => void; onRegenerate?: () => void; disabled?: boolean }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  const dis = disabled ? 'opacity-30 pointer-events-none' : 'cursor-pointer';
  return (
    <div className="flex items-center gap-0.5 mt-1 mr-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
      <button
        onClick={handleCopy}
        onMouseDown={(e) => e.preventDefault()}
        className="w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary hover:bg-black/5 transition-colors cursor-pointer"
        title={copied ? t(lang, 'copied') : t(lang, 'copy')}
      >
        {copied ? (
          <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square">
            <path d="M5 11.9657L8.37838 14.7529L15 5.83398" />
          </svg>
        ) : (
          <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M6.2513 6.24935V2.91602H17.0846V13.7493H13.7513M13.7513 6.24935V17.0827H2.91797V6.24935H13.7513Z" />
          </svg>
        )}
      </button>
      {onRewind && (
        <button
          onClick={onRewind}
          onMouseDown={(e) => e.preventDefault()}
          className={`w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary hover:bg-black/5 transition-colors ${dis}`}
          title={t(lang, 'rewind')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 7v6h6" />
            <path d="M21 17a9 9 0 0 0-15-6.7L3 13" />
          </svg>
        </button>
      )}
      {onRegenerate && (
        <button
          onClick={onRegenerate}
          onMouseDown={(e) => e.preventDefault()}
          className={`w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary hover:bg-black/5 transition-colors ${dis}`}
          title={t(lang, 'regenerate')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
          </svg>
        </button>
      )}
    </div>
  );
}

/**
 * 消息气泡组件
 *
 * 根据消息角色类型渲染不同的消息样式。
 *
 * @param props - 组件属性
 * @returns 返回消息气泡的 JSX 元素
 */
export default function MessageBubble({ item, toolInputMap, lang = 'zh-CN', onRewind, onRegenerate, hideReasoning, inlineReasoning, showActions = true, actionsDisabled }: MessageBubbleProps) {
  if (item.role === 'user') {
    return (
      <div className="flex justify-end py-1.5 group">
        <div className="flex flex-col items-end max-w-[min(82%,64ch)]">
          <div className="bg-surface-card-alt border border-border-light rounded-lg px-3 py-2 text-sm text-content-primary whitespace-pre-wrap break-words select-text">
            {item.text}
          </div>
          {showActions && <MessageActions text={item.text} lang={lang} onRewind={onRewind} disabled={actionsDisabled} />}
        </div>
      </div>
    );
  }

  if (item.role === 'assistant') {
    const reasoning = !hideReasoning && item.reasoning
      ? (inlineReasoning ? <ReasoningContent text={item.reasoning} /> : <ThinkingBlock text={item.reasoning} lang={lang} />)
      : null;
    return (
      <div className="py-1.5 animate-fade-in-up group">
        {reasoning}
        <div className="text-content-primary text-sm prose max-w-full select-text">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
            {item.text}
          </ReactMarkdown>
        </div>
        {showActions && <MessageActions text={item.text} lang={lang} onRegenerate={onRegenerate} disabled={actionsDisabled} />}
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
        <div className={`mt-1 ml-3.5 p-2.5 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-60 overflow-y-auto rounded-lg select-text ${isError ? 'text-danger bg-danger/5 border border-danger/20' : 'text-content-primary bg-surface-card-alt border border-border-light'}`}>
          {text}
        </div>
      )}
    </div>
  );
}

/**
 * 思考过程块组件
 *
 * 显示助手的思考/推理过程，支持折叠/展开。
 * 历史消息默认折叠以减少浏览器渲染负担（ReactMarkdown 渲染开销大），
 * 用户可点击标题展开查看完整思考过程。
 *
 * @param props - 组件属性
 * @param props.text - 思考过程文本
 * @param props.lang - UI 语言
 */
function ThinkingBlock({ text, lang }: { text: string; lang: UiLanguage }) {
  const [open, setOpen] = useState(false);
  if (!text?.trim()) return null;
  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-content-secondary hover:text-content-primary transition-colors py-0.5 cursor-pointer"
      >
        <svg
          className={`w-3 h-3 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M4.5 2.5L8 6L4.5 9.5" />
        </svg>
        <span className="font-medium">{t(lang, 'thinking_process')}</span>
      </button>
      {open && (
        <div className="text-sm text-content-secondary leading-relaxed select-text mt-1.5 opacity-80 py-1 animate-fade-in-up">
          <div className="prose prose-sm max-w-full">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
              {text}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 纯推理内容渲染（无折叠开关）
 *
 * 供 ChatArea 的 ThinkingProcessSection 统一渲染最终 assistant 消息的 reasoning，
 * 避免与 section 自身的折叠开关形成嵌套。
 *
 * @param props.text - 思考过程文本
 */
export function ReasoningContent({ text }: { text: string }) {
  if (!text?.trim()) return null;
  return (
    <div className="text-sm text-content-secondary leading-relaxed select-text opacity-80 py-1">
      <div className="prose prose-sm max-w-full">
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
          {text}
        </ReactMarkdown>
      </div>
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
        <div className="text-sm text-content-secondary leading-relaxed select-text mb-3 opacity-80 py-1">
          <div className="prose prose-sm max-w-full">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
              {reasoning}
            </ReactMarkdown>
          </div>
          {!hasText && <span className="inline-block w-0.5 h-4 bg-content-secondary animate-blink ml-0.5 align-middle" />}
        </div>
      )}
      {hasText && (
        <div className="text-content-primary text-sm prose max-w-full select-text">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
            {text}
          </ReactMarkdown>
          <span className="inline-block w-0.5 h-4 bg-primary animate-blink align-middle" />
        </div>
      )}
    </div>
  );
}
