/**
 * @fileoverview 提示输入组件
 *
 * Web 前端的用户输入组件，支持：
 * - 多行文本输入
 * - 命令自动补全（/ 前缀触发）
 * - 内联选项选择
 * - 快捷键支持（Enter 发送、Ctrl+Enter 换行、Esc 关闭）
 * - 忙碌状态下的停止按钮
 *
 * @module PromptInput
 */

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';
import type { WebWorkspaceItem } from '../types/protocol';

/**
 * Web 端允许的 B 类指令集合（自动补全只显示这些）
 *
 * A 类指令（new/resume/delete/model/effort/permissions/plan）已完全交由 UI 控件承载，
 * 输入框不识别；其余指令当作普通文本发给 LLM。因此自动补全只列出 B 类 10 个指令。
 */
// 自动补全列表：包含所有前端识别的斜杠指令
// 注意：'/agent' 虽在此列表中，但在 App.tsx 的 handleSubmit 中有特殊分支处理（分支选择器/创建向导/查看摘要）
// 因此 '/agent' 不在 B_COMMANDS 中，不会走 web_query 通道
export const WEB_COMMANDS = [
  '/rewind', '/compact', '/context', '/export', '/init',
  '/agent', '/turns', '/output-style', '/language', '/max-tokens', '/rename',
];

/**
 * 内联选项接口
 */
interface InlineOption {
  /** 选项值 */
  value: string;
  /** 显示标签 */
  label: string;
  /** 选项描述 */
  description?: string;
  /** 是否为当前活跃选项 */
  active?: boolean;
}

/**
 * 内联选项配置接口
 */
interface InlineOptions {
  /** 关联的命令名称 */
  command: string;
  /** 选项列表标题 */
  title: string;
  /** 选项列表 */
  options: InlineOption[];
}

/**
 * PromptInput 组件属性接口
 */
interface PromptInputProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 是否忙碌 */
  busy: boolean;
  /** 停止请求已发送、等待后端终止确认（终止过程可能有 1-2s 延迟，按钮显示旋转动画） */
  stopping?: boolean;
  /** 是否有运行中的后台任务（agent / bash / powershell 等，空闲时也可停止） */
  hasActiveTasks?: boolean;
  /** 是否已连接 */
  connected: boolean;
  /** 可用命令列表 */
  commands: string[];
  /** 提交回调 */
  onSubmit: (line: string) => void;
  /** 停止回调 */
  onStop: () => void;
  /** 内联选项配置（可选） */
  inlineOptions?: InlineOptions | null;
  /** 内联选项选择回调（可选） */
  onInlineSelect?: (command: string, value: string) => void;
  /** 内联选项关闭回调（可选） */
  onInlineClose?: () => void;
  /** 侧问请求进行中（可选） */
  btwLoading?: boolean;
  /** 侧问提交回调（可选） */
  onBtwSubmit?: (question: string) => void;
  /** 注册的工作区列表（目录按钮弹层数据源） */
  workspaces?: WebWorkspaceItem[];
  /** 当前活跃会话所属工作区目录（null 表示未知） */
  activeCwd?: string | null;
  /** 欢迎界面可见（无任何会话内容）：目录按钮常显，可直接选目录新建 */
  welcomeVisible?: boolean;
  /** 选择目录：立即在该目录新建会话并切换（选目录即新建） */
  onPickWorkspace?: (cwd: string) => void;
  /** 添加目录（弹层内联输入，后端校验并注册） */
  onAddWorkspace?: (path: string) => void;
  /** 打开设置弹窗的目录空间管理页 */
  onManageWorkspaces?: () => void;
  /** 底部工具行注入内容（Mode/Model/Effort 下拉，右对齐由发送/侧问按钮区隔离） */
  children?: React.ReactNode;
}

/**
 * 提示输入组件
 *
 * Web 前端的用户输入组件。
 *
 * @param props - 组件属性
 * @returns 返回提示输入的 JSX 元素
 */
export interface PromptInputHandle {
  /** 设置输入框内容（用于 rewind 回填被回退的 user 消息） */
  setDraft: (text: string) => void;
}

const PromptInput = forwardRef<PromptInputHandle, PromptInputProps>(function PromptInput({ lang, busy, stopping, hasActiveTasks, connected, commands, onSubmit, onStop, inlineOptions, onInlineSelect, onInlineClose, btwLoading, onBtwSubmit, workspaces, activeCwd, welcomeVisible, onPickWorkspace, onAddWorkspace, onManageWorkspaces, children }, ref) {
  const [value, setValue] = useState('');
  // + 号快捷指令菜单开关（与斜杠共用同一弹窗，展示全部 WEB_COMMANDS）
  const [plusOpen, setPlusOpen] = useState(false);
  // 目录选择弹层（选目录即新建会话）状态
  const [wsOpen, setWsOpen] = useState(false);
  const [wsAddMode, setWsAddMode] = useState(false);
  const [wsAddValue, setWsAddValue] = useState('');
  const wsInputRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    setDraft: (text: string) => {
      setValue(text);
      // 聚焦输入框并移到末尾，同时按内容自适应高度（onInput 不会因程序化赋值触发）
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (ta) {
          ta.focus();
          const len = text.length;
          ta.setSelectionRange(len, len);
          ta.style.height = 'auto';
          ta.style.height = Math.min(ta.scrollHeight, 140) + 'px';
          // 光标置于末尾：回填长草稿时滚动到底部，避免光标超出可视区
          ta.scrollTop = ta.scrollHeight;
        }
      });
    },
  }), []);
  const [showCommands, setShowCommands] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // 侧问内联输入框状态
  const [showBtwInput, setShowBtwInput] = useState(false);
  const [btwValue, setBtwValue] = useState('');
  const btwInputRef = useRef<HTMLInputElement>(null);
  const btwLoadingActive = btwLoading === true;
  const btwEnabled = typeof onBtwSubmit === 'function';

  // 消息发送后输入框清空时，重置高度（onInput 不会因程序化赋值触发）
  useEffect(() => {
    if (value === '' && textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value]);

  // 点击外部关闭内联选项
  useEffect(() => {
    if (!inlineOptions || inlineOptions.options.length === 0) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onInlineClose?.();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [inlineOptions, onInlineClose]);

  // 点击外部关闭命令补全（含 + 号菜单与目录弹层）
  useEffect(() => {
    if (!showCommands && !plusOpen && !wsOpen) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowCommands(false);
        setPlusOpen(false);
        setWsOpen(false);
        setWsAddMode(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showCommands, plusOpen, wsOpen]);

  // 自动补全仅显示 B 类指令（与后端 ready 推送的完整命令列表取交集，无交集则用静态集合）
  const webCommands = useMemo(() => {
    return commands.length > 0
      ? WEB_COMMANDS.filter((c) => commands.some((cmd) => cmd === c || cmd === c.slice(1)))
      : WEB_COMMANDS;
  }, [commands]);

  const filteredCommands = webCommands.filter((cmd) => {
    const query = value.toLowerCase();
    return cmd.toLowerCase().startsWith(query) || cmd.toLowerCase().includes(query.slice(1));
  });

  useEffect(() => {
    if (showCommands && listRef.current) {
      const selected = listRef.current.children[selectedIndex] as HTMLElement;
      selected?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex, showCommands]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    setPlusOpen(false);
    setShowCommands(newValue.startsWith('/') && newValue.length > 0 && filteredCommands.length > 0 && !inlineOptions);
  }, [filteredCommands.length, inlineOptions]);

  const selectCommand = useCallback((cmd: string) => {
    setValue('');
    setShowCommands(false);
    setPlusOpen(false);
    onSubmit(cmd);
  }, [onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // 内联选项模式
      if (inlineOptions) {
        const opts = inlineOptions.options;
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIndex((i) => Math.min(i + 1, opts.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIndex((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (opts[selectedIndex] && onInlineSelect) {
            onInlineSelect(inlineOptions.command, opts[selectedIndex].value);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          onInlineClose?.();
          return;
        }
        return;
      }

      // 自动补全模式
      if (showCommands) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSelectedIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSelectedIndex((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
          e.preventDefault();
          if (filteredCommands[selectedIndex]) {
            selectCommand(filteredCommands[selectedIndex]);
          }
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowCommands(false);
          return;
        }
      }

      // 普通输入模式
      if (e.key === 'Enter') {
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          const target = e.currentTarget;
          const start = target.selectionStart;
          const end = target.selectionEnd;
          const newValue = value.slice(0, start) + '\n' + value.slice(end);
          setValue(newValue);
          requestAnimationFrame(() => {
            target.selectionStart = target.selectionEnd = start + 1;
            target.style.height = 'auto';
            target.style.height = Math.min(target.scrollHeight, 140) + 'px';
            // 插入换行后光标可能超出可视区（textarea 内部滚动）：光标在末尾附近时滚到底部，
            // 避免用户手动滚动才能看到新行
            if (start + 1 >= newValue.length - 1) {
              target.scrollTop = target.scrollHeight;
            }
          });
          return;
        }
        e.preventDefault();
        if (busy || !connected) return;
        const line = value.trim();
        if (!line) return;
        onSubmit(line);
        // 始终清空输入框（包括 B 指令触发 inline popup 的情况）
        setValue('');
        setShowCommands(false);
        setPlusOpen(false);
      }
    },
    [value, busy, connected, onSubmit, showCommands, filteredCommands, selectedIndex, selectCommand, inlineOptions, onInlineSelect, onInlineClose],
  );

  const handleSend = () => {
    // busy 或（有后台任务运行且输入框为空）→ 停止任务
    if (busy || (hasActiveTasks && !value.trim())) {
      onStop();
      return;
    }
    if (!connected) return;
    const line = value.trim();
    if (!line) return;
    onSubmit(line);
    setValue('');
    setShowCommands(false);
    setPlusOpen(false);
  };

  /**
   * 提交侧问问题
   *
   * 校验非空且未在 loading 中后调用 onBtwSubmit 回调，并关闭内联输入框。
   */
  const handleBtwSubmit = () => {
    if (btwLoadingActive) return;
    const q = btwValue.trim();
    if (!q) return;
    onBtwSubmit?.(q);
    setBtwValue('');
    setShowBtwInput(false);
  };

  /**
   * 切换侧问输入框显示
   *
   * 关闭时清空已输入内容；打开时延迟聚焦输入框。
   * loading 进行中禁止再次打开/关闭以避免状态错乱。
   */
  const toggleBtwInput = () => {
    if (btwLoadingActive) return;
    setShowBtwInput((prev) => {
      const next = !prev;
      if (!next) setBtwValue('');
      if (next) setTimeout(() => btwInputRef.current?.focus(), 0);
      return next;
    });
  };

  /**
   * 侧问输入框键盘事件处理
   *
   * - Enter：提交（与按钮点击等效）
   * - Esc：取消并关闭输入框
   * - Ctrl+B：也触发提交（与点击按钮等效，兼容任务约定）
   *
   * @param e - 键盘事件
   */
  const handleBtwKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleBtwSubmit();
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      setBtwValue('');
      setShowBtwInput(false);
      return;
    }
    // Ctrl+B / Cmd+B：与点击侧问按钮等效，触发提交
    if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
      e.preventDefault();
      handleBtwSubmit();
    }
  };

  const showInline = inlineOptions && inlineOptions.options.length > 0;
  const showAutocomplete = showCommands && filteredCommands.length > 0 && !showInline;
  // + 号与斜杠共用同一命令弹窗（+ 展示全部 WEB_COMMANDS，斜杠展示过滤结果）
  const showMenu = plusOpen || showAutocomplete;
  const menuCommands = plusOpen ? webCommands : filteredCommands;
  // 发送按钮状态：停止（busy 或后台任务+空输入）｜空输入灰色（不可发送）｜正常发送
  const isStopState = busy || (hasActiveTasks && !value.trim());
  const isIdleEmpty = !value.trim() && !busy && !stopping && !isStopState;

  return (
    <div className="relative px-3 pt-3" ref={containerRef}>
      {/* 内联选项 */}
      {showInline && (
        <div className="absolute bottom-full left-3 right-3 mb-1 glass-surface rounded-2xl max-h-64 overflow-y-auto py-1.5 z-20">
          <div className="px-3 py-1.5 text-[10px] text-content-disabled font-semibold uppercase tracking-widest">{inlineOptions.title}</div>
          {inlineOptions.options.map((opt, idx) => (
            <button
              key={opt.value}
              onClick={() => onInlineSelect?.(inlineOptions.command, opt.value)}
              className={`w-full text-left px-3 py-2 text-sm transition-colors cursor-pointer flex flex-col gap-0.5 rounded-md ${
                idx === selectedIndex ? 'glass-option-active text-content-primary' : opt.active ? 'text-primary/70 glass-option-hover' : 'text-content-secondary glass-option-hover'
              }`}
            >
              <span className="font-medium">{opt.label}</span>
              {opt.description && <span className="text-xs text-content-disabled">{opt.description}</span>}
            </button>
          ))}
        </div>
      )}

      {/* + 号 / 斜杠共用的命令弹窗（同一位置、同一样式） */}
      {showMenu && (
        <div
          ref={listRef}
          className="absolute bottom-full left-3 right-3 mb-1 glass-surface rounded-2xl max-h-56 overflow-y-auto py-1.5 z-20 animate-fade-in-up scrollbar-hidden"
        >
          <div className="px-3 py-1.5 text-[10px] text-content-disabled font-semibold uppercase tracking-widest">Commands</div>
          {menuCommands.map((cmd, idx) => (
            <button
              key={cmd}
              onClick={() => selectCommand(cmd)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors cursor-pointer animate-fade-in-up rounded-md ${
                (!plusOpen && idx === selectedIndex) ? 'glass-option-active text-content-primary' : 'text-content-secondary glass-option-hover'
              }`}
              style={{ animationDelay: `${idx * 30}ms` }}
            >
              <span className="font-mono shrink-0">{cmd}</span>
              <span className="text-xs text-content-disabled truncate flex-1 text-left">{t(lang, `cmd_${cmd.slice(1).replace(/-/g, '_')}`)}</span>
            </button>
          ))}
        </div>
      )}

      {/* 侧问内联输入框（textarea 上方），busy 时隐藏 */}
      {btwEnabled && !busy && showBtwInput && (
        <div className="absolute bottom-full left-3 right-3 mb-1 glass-surface rounded-2xl px-3 py-2 z-20 animate-fade-in-up flex items-center gap-2 transition-all duration-200 focus-within:shadow-glow focus-within:border-primary/40">
          <span className="text-[10px] text-content-disabled font-semibold uppercase tracking-widest shrink-0">{t(lang, 'btw_button')}</span>
          <input
            ref={btwInputRef}
            type="text"
            value={btwValue}
            onChange={(e) => setBtwValue(e.target.value)}
            onKeyDown={handleBtwKeyDown}
            placeholder={t(lang, 'btw_placeholder')}
            disabled={btwLoadingActive}
            className="flex-1 min-w-0 bg-transparent text-sm text-content-primary placeholder-content-disabled outline-none border-none disabled:opacity-50"
          />
          <button
            onClick={handleBtwSubmit}
            disabled={btwLoadingActive || !btwValue.trim()}
            title={t(lang, 'send')}
            className="shrink-0 px-2 py-1 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {t(lang, 'send')}
          </button>
        </div>
      )}

      {/* 输入区：仅 textarea（字体与主聊天区普通 text 一致） */}
      <div className="flex items-end">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={connected ? t(lang, 'input_placeholder') : t(lang, 'disconnected')}
          rows={1}
          disabled={!connected}
          className="flex-1 resize-none bg-transparent text-base text-content-primary placeholder-content-disabled min-h-[36px] max-h-[140px] focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed leading-[1.8] py-2 pl-3 pr-2 scrollbar-hidden"
          style={{ height: 'auto', overflowY: 'auto' }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 140) + 'px';
          }}
        />
      </div>

      {/* 底部工具行：+ 号 + 目录选择 + Mode/Model/Effort（左），侧问/发送按钮（右）；pt-4 与输入区留出视觉空白行 */}
      <div className="flex items-center justify-between gap-2 px-1 pt-4 pb-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* + 号：打开快捷指令菜单（与斜杠同一弹窗） */}
          <button
            onClick={() => { setPlusOpen((o) => !o); setShowCommands(false); setWsOpen(false); }}
            title="Commands"
            aria-label="Commands"
            className={`pill-badge w-8 h-8 flex items-center justify-center rounded-full transition-colors cursor-pointer ${
              plusOpen ? 'text-primary' : 'text-content-secondary hover:text-content-primary'
            }`}
          >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 3v10M3 8h10" />
            </svg>
          </button>
          {/* 目录选择：欢迎界面可见（点选目录即在该目录新建会话）；无三角指示器。
              弹层标题与 ToolBar 下拉（Mode/Model/Effort）同风格：英文、uppercase */}
          {welcomeVisible && (
          <div className="relative shrink-0">
            <button
              onClick={() => { setWsOpen((o) => !o); setPlusOpen(false); setShowCommands(false); setWsAddMode(false); }}
              disabled={!connected || !onPickWorkspace}
              title={activeCwd ? `${t(lang, 'workspace_new_in')}\n${activeCwd}` : t(lang, 'workspace_select')}
              className={`pill-badge flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-full transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                wsOpen ? 'text-primary' : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1.5 4.5v7a1.5 1.5 0 001.5 1.5h10a1.5 1.5 0 001.5-1.5V6.5a1.5 1.5 0 00-1.5-1.5H8L6.4 3.1a1.5 1.5 0 00-1.1-.6H3a1.5 1.5 0 00-1.5 1.5v.5z" />
              </svg>
              <span className={`max-w-[110px] truncate ${activeCwd ? '' : 'text-content-disabled'}`}>
                {activeCwd ? (workspaces?.find((w) => w.path === activeCwd)?.name || activeCwd.split(/[\\/]/).filter(Boolean).pop() || activeCwd) : t(lang, 'workspace_label')}
              </span>
            </button>
            {wsOpen && (
              <div className="absolute bottom-full left-0 mb-1 glass-surface rounded-2xl z-20 min-w-[260px] max-w-[380px] py-1.5 max-h-[40vh] overflow-y-auto animate-scale-in dropdown-origin-bottom-left dropdown-scroll">
                {/* 标题与 ToolBar 下拉一致：英文、10px、uppercase、居中，无截断 */}
                <div className="px-3 py-1.5 text-[10px] text-content-disabled font-semibold uppercase tracking-widest text-center border-b border-border-light mb-1">New session in</div>
                {(workspaces ?? []).map((ws) => {
                  const isActive = ws.path === activeCwd;
                  return (
                    <button
                      key={ws.path}
                      onClick={() => { setWsOpen(false); onPickWorkspace?.(ws.path); }}
                      title={ws.path}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors cursor-pointer rounded-md ${
                        isActive ? 'text-primary font-medium' : 'text-content-secondary glass-option-hover'
                      } ${!ws.available ? 'opacity-50' : ''}`}
                    >
                      <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1.5 4.5v7a1.5 1.5 0 001.5 1.5h10a1.5 1.5 0 001.5-1.5V6.5a1.5 1.5 0 00-1.5-1.5H8L6.4 3.1a1.5 1.5 0 00-1.1-.6H3a1.5 1.5 0 00-1.5 1.5v.5z" />
                      </svg>
                      <span className="truncate flex-1 text-left">{ws.name}</span>
                      {ws.is_default && <span className="text-[10px] text-content-disabled shrink-0">{t(lang, 'workspace_default_badge')}</span>}
                      {isActive && (
                        <svg className="w-4 h-4 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3.5 8.5l3 3 6-7" />
                        </svg>
                      )}
                    </button>
                  );
                })}
                {wsAddMode ? (
                  <div className="px-2.5 py-2 border-t border-border-light mt-1">
                    <div className="flex items-center gap-1.5">
                      <input
                        ref={wsInputRef}
                        type="text"
                        value={wsAddValue}
                        onChange={(e) => setWsAddValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const v = wsAddValue.trim();
                            if (v) { onAddWorkspace?.(v); setWsAddValue(''); setWsAddMode(false); }
                          } else if (e.key === 'Escape') {
                            setWsAddMode(false); setWsAddValue('');
                          }
                        }}
                        autoFocus
                        placeholder={t(lang, 'workspace_add_placeholder')}
                        className="flex-1 min-w-0 bg-transparent text-sm text-content-primary placeholder-content-disabled outline-none border border-border-light rounded-md px-2 py-1.5 focus:border-primary/40"
                      />
                      <button
                        onClick={() => { const v = wsAddValue.trim(); if (v) { onAddWorkspace?.(v); setWsAddValue(''); setWsAddMode(false); } }}
                        disabled={!wsAddValue.trim()}
                        className="shrink-0 px-2.5 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {t(lang, 'workspace_add_confirm')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => { setWsAddMode(true); requestAnimationFrame(() => wsInputRef.current?.focus()); }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-content-secondary glass-option-hover transition-colors cursor-pointer rounded-md border-t border-border-light mt-1"
                  >
                    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M8 3v10M3 8h10" />
                    </svg>
                    <span>{t(lang, 'workspace_add')}</span>
                  </button>
                )}
                {onManageWorkspaces && (
                  <button
                    onClick={() => { setWsOpen(false); onManageWorkspaces(); }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-content-secondary glass-option-hover transition-colors cursor-pointer rounded-md"
                  >
                    <svg className="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                    </svg>
                    <span>{t(lang, 'workspace_manage')}</span>
                  </button>
                )}
              </div>
            )}
          </div>
          )}
          {children}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {/* 侧问按钮：发送按钮左侧，仅在 btwEnabled 且非 busy 时显示 */}
          {btwEnabled && !busy && (
            <button
              onClick={toggleBtwInput}
              disabled={btwLoadingActive}
              title={t(lang, 'btw_button')}
              className={`shrink-0 w-8 h-8 flex items-center justify-center rounded-full transition-colors duration-150 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                showBtwInput
                  ? 'bg-primary-light text-primary border border-primary/30'
                  : 'text-content-secondary glass-option-hover hover:text-primary'
              }`}
            >
              {btwLoadingActive ? (
                <svg className="w-4 h-4 animate-spin text-primary" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                  <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              ) : (
                <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 4.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 14 4.5v5A1.5 1.5 0 0 1 12.5 11H7l-3 2.5V11H3.5A1.5 1.5 0 0 1 2 9.5v-5z" />
                  <path d="M5.5 7h5M5.5 5.5h3" />
                </svg>
              )}
            </button>
          )}
          <button
            onClick={handleSend}
            disabled={(!connected && !busy) || stopping}
            className={`shrink-0 w-8 h-8 flex items-center justify-center rounded-full transition-colors duration-150 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
              stopping
                ? 'bg-danger/10 text-danger hover:bg-danger/20'
                : isStopState
                  ? 'bg-danger/10 text-danger hover:bg-danger/20 animate-pulse'
                  : isIdleEmpty
                    ? 'bg-black/10 text-content-disabled cursor-not-allowed pointer-events-none'
                    : 'bg-primary text-white hover:bg-primary-hover hover:shadow-glow'
            }`}
            title={stopping ? t(lang, 'task_stopping') : isStopState ? t(lang, 'task_stopped') : t(lang, 'send')}
          >
            {stopping ? (
              // 停止请求已发出、等待后端确认：旋转圆圈缓冲动画（终止可能延迟 1-2s）
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            ) : isStopState
              ? <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><rect width="10" height="10" rx="1.5" /></svg>
              : '↑'}
          </button>
        </div>
      </div>
    </div>
  );
});

export default PromptInput;
