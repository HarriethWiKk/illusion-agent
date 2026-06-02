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

import { useCallback, useEffect, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

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
}

/**
 * 提示输入组件
 *
 * Web 前端的用户输入组件。
 *
 * @param props - 组件属性
 * @returns 返回提示输入的 JSX 元素
 */
export default function PromptInput({ lang, busy, connected, commands, onSubmit, onStop, inlineOptions, onInlineSelect, onInlineClose }: PromptInputProps) {
  const [value, setValue] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const filteredCommands = commands.filter((cmd) => {
    const query = value.toLowerCase();
    return cmd.toLowerCase().startsWith(query) || cmd.toLowerCase().includes(query.slice(1));
  });

  // 当 inlineOptions 变化时重置选中索引
  useEffect(() => { setSelectedIndex(0); }, [inlineOptions, value]);

  useEffect(() => {
    if (showCommands && listRef.current) {
      const selected = listRef.current.children[selectedIndex] as HTMLElement;
      selected?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex, showCommands]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    setShowCommands(newValue.startsWith('/') && newValue.length > 0 && filteredCommands.length > 0 && !inlineOptions);
  }, [filteredCommands.length, inlineOptions]);

  const selectCommand = useCallback((cmd: string) => {
    setValue('');
    setShowCommands(false);
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
          });
          return;
        }
        e.preventDefault();
        if (busy || !connected) return;
        const line = value.trim();
        if (!line) return;
        onSubmit(line);
        setValue('');
        setShowCommands(false);
      }
    },
    [value, busy, connected, onSubmit, showCommands, filteredCommands, selectedIndex, selectCommand, inlineOptions, onInlineSelect, onInlineClose],
  );

  const handleSend = () => {
    if (busy) {
      onStop();
      return;
    }
    if (!connected) return;
    const line = value.trim();
    if (!line) return;
    onSubmit(line);
    setValue('');
    setShowCommands(false);
  };

  const showInline = inlineOptions && inlineOptions.options.length > 0;
  const showAutocomplete = showCommands && filteredCommands.length > 0 && !showInline;

  return (
    <div className="px-4 md:px-5 pb-4 pt-2 relative">
      {/* 内联选项 */}
      {showInline && (
        <div className="absolute bottom-full left-4 right-4 md:left-5 md:right-5 mb-1 bg-white border border-border-light rounded-xl shadow-lg max-h-64 overflow-y-auto py-1 z-20">
          <div className="px-3 py-1.5 text-xs text-content-disabled font-medium">{inlineOptions.title}</div>
          {inlineOptions.options.map((opt, idx) => (
            <button
              key={opt.value}
              onClick={() => onInlineSelect?.(inlineOptions.command, opt.value)}
              className={`w-full text-left px-3 py-2 text-sm transition-colors cursor-pointer flex flex-col gap-0.5 ${
                idx === selectedIndex ? 'bg-primary-light text-primary' : opt.active ? 'bg-surface-hover text-content-primary' : 'text-content-secondary hover:bg-surface-hover'
              }`}
            >
              <span className="font-medium">{opt.label}</span>
              {opt.description && <span className="text-xs text-content-disabled">{opt.description}</span>}
            </button>
          ))}
        </div>
      )}

      {/* 自动补全列表 */}
      {showAutocomplete && (
        <div
          ref={listRef}
          className="absolute bottom-full left-4 right-4 md:left-5 md:right-5 mb-1 bg-white border border-border-light rounded-xl shadow-lg max-h-56 overflow-y-auto py-1 z-20"
        >
          {filteredCommands.map((cmd, idx) => (
            <button
              key={cmd}
              onClick={() => selectCommand(cmd)}
              className={`w-full text-left px-3 py-2 text-sm transition-colors cursor-pointer ${
                idx === selectedIndex ? 'bg-primary-light text-primary' : 'text-content-secondary hover:bg-surface-hover'
              }`}
            >
              <span className="font-mono">{cmd}</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end bg-white rounded-[12px] border border-border-light shadow-soft">
        <textarea
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={connected ? t(lang, 'input_placeholder') : t(lang, 'disconnected')}
          rows={1}
          disabled={!connected}
          className="flex-1 resize-none bg-transparent outline-none text-sm text-content-primary placeholder-content-disabled min-h-[36px] max-h-[140px] disabled:opacity-50 leading-normal py-2.5 pl-3 pr-2"
          style={{ height: 'auto', overflow: 'hidden' }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 140) + 'px';
          }}
        />
        <button
          onClick={handleSend}
          disabled={!connected && !busy}
          className={`shrink-0 m-1.5 w-8 h-8 flex items-center justify-center rounded-full transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
            busy
              ? 'bg-red-100 text-danger hover:bg-red-200 animate-pulse'
              : 'bg-primary text-white hover:bg-primary-hover'
          }`}
          title={busy ? t(lang, 'task_stopped') : t(lang, 'send')}
        >
          {busy ? '■' : '↑'}
        </button>
      </div>
    </div>
  );
}
