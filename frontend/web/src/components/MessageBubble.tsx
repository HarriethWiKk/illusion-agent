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

import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkSuperscript from '../remarkSuperscript';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import 'highlight.js/styles/github.css';
import { t, type UiLanguage } from '../i18n';
import { toolDisplayName } from '../utils/toolDisplayName';
import { renderAnsi } from '../utils/ansi';
import { openImagePreview } from '../utils/imagePreview';
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

/** 图片文件 URL 判定（含 query/hash 后缀，如 https://x.com/a.png?raw=1） */
const IMAGE_URL_RE = /\.(png|jpe?g|gif|webp|bmp|svg|avif|ico)(\?.*)?(#.*)?$/i;

/**
 * 自定义 markdown 组件
 *
 * - pre：代码块顶栏（语言名 + 复制按钮）
 * - img：点击在应用内打开图片预览（不跳转外部浏览器，避免桌面端被困）
 * - a：图片链接（href 指向图片文件）同样在应用内预览；其余链接保持默认行为
 */
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
  img: ({ src, alt, ...rest }: React.ComponentPropsWithoutRef<'img'>) => (
    <img
      {...rest}
      src={src}
      alt={alt}
      loading="lazy"
      onClick={() => src && openImagePreview(src)}
      className="cursor-zoom-in max-w-full h-auto rounded"
    />
  ),
  a: ({ href, children, ...rest }: React.ComponentPropsWithoutRef<'a'>) => (
    <a
      {...rest}
      href={href}
      onClick={(e) => {
        // 图片链接在应用内预览（桌面端不会被外链拦截器重定向到系统浏览器）
        if (href && IMAGE_URL_RE.test(href)) {
          e.preventDefault();
          openImagePreview(href);
        }
      }}
    >
      {children}
    </a>
  ),
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
  /** 是否显示操作按钮（复制/撤销） */
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
export default function MessageBubble({ item, toolInputMap, lang = 'zh-CN', onRewind, onRegenerate, hideReasoning, showActions = true, actionsDisabled }: MessageBubbleProps) {
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
    const reasoning = !hideReasoning && item.reasoning ? <ThinkingBlock text={item.reasoning} lang={lang} /> : null;
    return (
      <div className="py-1.5 group">
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

  // plan 角色由 ModalCard 专门展示，不在对话流中重复显示
  if (item.role === 'plan') {
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
 * 完成态默认折叠（标题行 + 摘要）；展开后先显示执行期间保留的流式进度
 * （agent 子任务的思考过程——仅供人查看，不进入 LLM 上下文），再显示
 * 工具结果正文。流式阶段由 PendingToolBubble 展示同一份进度，完成后无缝衔接。
 *
 * @param props - 组件属性
 * @param props.name - 工具名称
 * @param props.text - 结果文本
 * @param props.isError - 是否为错误结果
 * @param props.toolInput - 工具输入参数
 */
function ToolResultBubble({ name, text, isError, toolInput }: { name: string; text: string; isError?: boolean; toolInput?: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  // summarizeInput 用原名做大小写不敏感匹配，显示名用映射后的友好名
  const summary = summarizeInput(name, toolInput, name);
  // agent 工具根据 subagent_type 动态显示类型名，其他工具使用映射表
  const displayName = name === 'agent' && toolInput ? getAgentDisplayName(toolInput) : toolDisplayName(name);
  // 任务完成后直接用最终结果替换：流式阶段已累积展示思考过程，
  // 完成后仅以最终结果（text）作为正文，不再保留/判断思考过程
  const hasContent = !!text;

  return (
    <div className="py-1.5">
      <button
        onClick={() => hasContent && setOpen(!open)}
        className={`flex items-start text-base transition-colors cursor-pointer text-left ${hasContent ? 'text-content-secondary hover:text-content-primary' : ''}`}
      >
        {/* 圆点右移 3px 使其对称轴（7px）与大脑图标重合；文本缩进不变
            （3px + 8px + 9px = 14px + 6px = 20px）；mt-2 垂直居中 */}
        <span className={`inline-block w-2 h-2 rounded-full shrink-0 mt-2 ml-[3px] mr-[9px] ${isError ? 'bg-danger' : 'bg-primary'}`} />
        <span>
          <span className={isError ? 'text-danger' : 'text-content-primary'}>{displayName}</span>
          {/* 预览行在展开/折叠时均保留，展开后与结果正文并存；字号介于工具名与正文之间 */}
          {summary && <span className={`text-sm ${isError ? 'text-danger' : 'text-content-disabled'}`}>（{summary}）</span>}
          {isError && <span className="text-xs text-danger font-medium"> ERROR</span>}
        </span>
      </button>
      {open && hasContent && (
        <div className={`mt-1 ml-3.5 p-2.5 font-mono text-xs leading-relaxed max-h-96 overflow-y-auto scrollbar-hidden rounded-lg select-text ${isError ? 'text-danger bg-danger/5 border border-danger/20' : 'text-content-primary bg-surface-card-alt border border-border-light'}`}>
          {text && (
            <div className="whitespace-pre-wrap break-words">{renderAnsi(text)}</div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * 流式进度消息渲染（供 PendingToolBubble 使用）
 *
 * thinking/text 为增量流式片段（token 级累积，完成后不再有光标），
 * tool/status 为完整消息，加 ▸ 前缀。
 */
function ProgressMessages({ messages, showCursor }: { messages: Array<{message: string; type?: string}>; showCursor?: boolean }) {
  const lastIdx = messages.length - 1;
  return (
    <>
      {messages.map((msg, i) => (
        <div key={i} className="py-px">
          {msg.message.split('\n').map((line, li) => (
            <div key={li}>
              {li === 0 && msg.type !== 'thinking' && msg.type !== 'text' && (
                <span className="text-primary/70 mr-1">▸</span>
              )}
              {line || '\u00A0'}
              {showCursor && i === lastIdx && li === 0 && (msg.type === 'thinking' || msg.type === 'text') && (
                <span className="inline-block w-0.5 h-3 bg-primary animate-blink ml-0.5 align-middle" />
              )}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

/**
 * 思考过程块组件（独立折叠单元）
 *
 * 显示助手的思考/推理过程，支持折叠/展开。每个思考过程块独立折叠，
 * 互不影响（对齐 opencode 的 part 级独立折叠）。
 *
 * 自动折叠：`autoCollapsed` 信号变化（如 text 推入）时自动折叠/展开，
 * 但用户手动点击过的块不再被自动信号覆盖，尊重用户选择。
 *
 * 点击内容区域本身也可折叠（无需翻回顶部标题处），但不会打断
 * 文本选中/复制、链接点击、代码块复制按钮等交互。
 *
 * @param props - 组件属性
 * @param props.text - 思考过程文本
 * @param props.lang - UI 语言
 * @param props.defaultOpen - 初始展开状态（默认折叠）
 * @param props.autoCollapsed - 自动折叠信号：true 折叠、false 展开，仅对用户未手动操作过的块生效
 * @param props.streaming - 是否正在流式输出（大脑图标切换为与工具行圆点一致的脉冲动画，展开内容底部显示流式光标）
 */
export function ThinkingBlock({
  text,
  lang,
  defaultOpen = false,
  autoCollapsed,
  streaming,
}: {
  text: string;
  lang: UiLanguage;
  defaultOpen?: boolean;
  autoCollapsed?: boolean;
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // 用户是否手动操作过（展开/折叠）此块：手动操作后自动折叠信号不再覆盖
  const interactedRef = useRef(false);
  // 待执行的点击折叠定时器：双击选词的第一击会触发 click（detail=1），
  // 立即折叠会破坏双击/三击选词，故延迟折叠并允许 onDoubleClick 取消
  const collapseTimerRef = useRef<number | undefined>(undefined);
  // React 官方 "adjusting state during render" 模式：prev 值用 state 存储，
  // 避免并发渲染（Suspense/transition 中断）下 ref 先写而 setState 未提交
  const [prevAutoCollapsed, setPrevAutoCollapsed] = useState(autoCollapsed);

  // autoCollapsed 信号变化时同步状态；用户手动操作过的块保持用户选择
  if (autoCollapsed !== prevAutoCollapsed) {
    setPrevAutoCollapsed(autoCollapsed);
    if (!interactedRef.current) setOpen(!autoCollapsed);
  }

  // 组件卸载时清除待执行的折叠定时器
  useEffect(() => {
    return () => {
      if (collapseTimerRef.current !== undefined) {
        window.clearTimeout(collapseTimerRef.current);
      }
    };
  }, []);

  if (!text?.trim()) return null;

  const handleToggle = () => {
    interactedRef.current = true;
    setOpen(!open);
  };

  /** 点击已展开的内容区域折叠（不打断选中/复制/链接/复制按钮/双击选词） */
  const handleContentClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.detail > 1) return; // 双击第二击（此时已选中词）：不折叠
    const target = e.target as HTMLElement;
    // 交互元素交给默认行为：链接跳转、代码块复制按钮等
    if (target.closest('a, button, input, textarea')) return;
    // 正在选中文本（复制场景）不折叠
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    // 延迟折叠（300ms）：双击的第一击 detail 也是 1，立即折叠会破坏
    // 双击选词/三击选段；onDoubleClick 会在此窗口内取消定时器
    collapseTimerRef.current = window.setTimeout(() => {
      collapseTimerRef.current = undefined;
      interactedRef.current = true;
      setOpen(false);
    }, 300);
  };

  /** 双击（选词）取消待执行的折叠 */
  const handleContentDoubleClick = () => {
    if (collapseTimerRef.current !== undefined) {
      window.clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = undefined;
    }
  };

  return (
    <div className="mb-1.5">
      <button
        onClick={handleToggle}
        className="flex items-center gap-1.5 text-base text-content-primary leading-[1.8] transition-colors py-1.5 cursor-pointer"
      >
        {/* 大脑图标：思考过程标识（行高与中间 text 的 prose 1.8 对齐；流式时与工具行圆点一致的脉冲动画） */}
        <svg className={`w-3.5 h-3.5 shrink-0 text-primary ${streaming ? 'animate-pulse-scale' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
          <path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01" />
        </svg>
        <span>{t(lang, 'thinking_process')}</span>
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
      </button>
      {open && (
        <div onClick={handleContentClick} onDoubleClick={handleContentDoubleClick} className="relative">
          <div className="text-sm text-content-secondary leading-relaxed select-text mt-1.5 opacity-80 py-1">
            <div className="prose prose-sm max-w-full">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkSuperscript]} rehypePlugins={[rehypeHighlight, rehypeRaw]} components={mdComponents}>
                {text}
              </ReactMarkdown>
            </div>
            {streaming && <span className="inline-block w-0.5 h-3 bg-content-secondary animate-blink ml-0.5 align-middle" />}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 待处理工具调用气泡组件
 *
 * 显示正在执行的工具调用，带有脉冲动画效果。
 *
 * 默认折叠只显示工具名与摘要（对齐 opencode：工具默认折叠为标题行）；
 * 用户可点击标题行展开查看全部进度消息（web 端不受 terminal 行数限制）。
 * 工具完成（completed）后由 ToolResultBubble（同样默认折叠）替代。
 *
 * @param props - 组件属性
 * @param props.call - 待处理的工具调用信息
 */
export function PendingToolBubble({ call }: { call: PendingToolCall }) {
  // 工具执行中默认展开（可实时查看执行过程；仅 agent 工具会上报进度消息，
  // 普通工具无进度时展开态只显示标题行）；完成后由 ToolResultBubble 折叠展示
  const [open, setOpen] = useState(true);
  // 与 terminal 端 BlinkingToolIndicator 对齐：tool_input 未到达时 summary 为空，
  // 只显示工具名；到达后始终在同一行显示命令摘要，不随进度区折叠而隐藏
  const summary = call.tool_input ? summarizeInput(call.tool_name, call.tool_input) : '';
  // agent 工具根据 subagent_type 动态显示类型名，其他工具使用映射表
  const displayName = call.tool_name === 'agent' && call.tool_input
    ? getAgentDisplayName(call.tool_input as Record<string, unknown>)
    : toolDisplayName(call.tool_name);
  const progressMessages = call.progressMessages ?? [];
  // thinking/text 为增量流式片段（token 级累积），tool/status 为完整消息
  const lastMsg = progressMessages.length > 0 ? progressMessages[progressMessages.length - 1] : undefined;
  const hasStreamingTail = !!lastMsg && (lastMsg.type === 'thinking' || lastMsg.type === 'text');
  // 内容累积时的自动跟随：用户未上滑过内部容器时无条件跟随（大段进度增量
  // 也能跟上）；上滑过则仅滚回底部附近时恢复。程序滚动（auto-scroll 赋值）
  // 派生的 scroll 事件用 programmaticScrollRef 忽略。
  const progressRef = useRef<HTMLDivElement>(null);
  const programmaticScrollRef = useRef(false);
  const userScrolledRef = useRef(false); // 用户上滑过容器内部 → 暂停跟随
  useEffect(() => {
    const el = progressRef.current;
    if (!el) return;
    if (userScrolledRef.current) {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distance > 24) return; // 用户上滑中，不打扰
      userScrolledRef.current = false; // 滚回底部附近，恢复跟随
    }
    const prevTop = el.scrollTop;
    el.scrollTop = el.scrollHeight;
    if (el.scrollTop !== prevTop) programmaticScrollRef.current = true;
  }, [progressMessages]);
  const handleProgressScroll = useCallback(() => {
    if (programmaticScrollRef.current) {
      programmaticScrollRef.current = false;
      return; // 程序滚动触发的事件，忽略
    }
    const el = progressRef.current;
    if (!el) return;
    const max = el.scrollHeight - el.clientHeight;
    userScrolledRef.current = el.scrollTop < max - 24; // 滚到接近底部视为"跟随模式"
  }, []);
  return (
    <div className="py-1.5">
      <button
        onClick={() => progressMessages.length > 0 && setOpen(!open)}
        className={`flex items-start text-base transition-colors cursor-pointer text-left ${progressMessages.length > 0 ? 'text-content-secondary hover:text-content-primary' : ''}`}
      >
        {/* 圆点右移 3px 使其对称轴（7px）与大脑图标重合；文本缩进不变；mt-2 垂直居中 */}
        <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse-scale shrink-0 mt-2 ml-[3px] mr-[9px]" />
        <span className="flex-1 min-w-0">
          <span className="text-content-primary">{displayName}</span>
          {summary && <span className="text-sm text-content-disabled">（{summary}）</span>}
        </span>
      </button>
      {open && progressMessages.length > 0 && (
        <div
          ref={progressRef}
          onScroll={handleProgressScroll}
          className="mt-1 ml-3.5 p-2.5 whitespace-pre-wrap font-mono text-xs leading-relaxed max-h-96 overflow-y-auto scrollbar-hidden rounded-lg select-text text-content-secondary bg-surface-card-alt border border-border-light"
        >
          <ProgressMessages messages={progressMessages} showCursor={hasStreamingTail} />
        </div>
      )}
    </div>
  );
}

// ---- Agent 工具显示名辅助函数 ----

/**
 * 根据 tool_input 中的 subagent_type 获取 agent 工具的显示名
 * input 完全未到达时返回 "Agent"，到达后无 subagent_type 返回 "GeneralPurpose"
 */
function getAgentDisplayName(toolInput?: Record<string, unknown>): string {
	// input 完全未到达时显示 "Agent"；到达后无 subagent_type 则默认 "GeneralPurpose"
	if (!toolInput || Object.keys(toolInput).length === 0) {
		return 'Agent';
	}
	const agentType = toolInput.subagent_type ?? 'general-purpose';
	// 转 PascalCase：general-purpose → GeneralPurpose, explore → Explore
	return String(agentType)
		.replace(/_/g, '-')
		.split('-')
		.map(w => w.charAt(0).toUpperCase() + w.slice(1))
		.join('');
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
 * 自动折叠模型（对齐 opencode 的 part 级独立折叠）：
 * - 思考过程流式时默认展开，用户可随时折叠/展开
 * - text 推入时自动折叠其上方思考过程（text 保留可见），
 *   用户手动展开过的思考过程不被自动折叠覆盖
 *
 * @param props - 组件属性
 * @param props.text - 正文文本
 * @param props.reasoning - 思考过程文本（可选）
 * @param props.lang - UI 语言
 */
export function StreamingBuffer({ text, reasoning, lang }: { text: string; reasoning?: string; lang: UiLanguage }) {
  const hasReasoning = !!reasoning && !!reasoning.trim();
  const hasText = !!text && !!text.trim();

  return (
    <div className="py-1.5">
      {hasReasoning && (
        <ThinkingBlock
          text={reasoning}
          lang={lang}
          streaming
          defaultOpen={!hasText}
          autoCollapsed={hasText}
        />
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
