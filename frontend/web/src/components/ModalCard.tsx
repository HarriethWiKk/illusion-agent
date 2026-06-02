/**
 * @fileoverview 模态卡片组件
 *
 * Web 前端的模态对话框组件，支持：
 * - 权限请求卡片（允许/拒绝/总是允许）
 * - 问答卡片（单选/多选/自定义输入）
 *
 * @module ModalCard
 */

import { useCallback, useEffect, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

/**
 * 问题选项接口
 */
interface QuestionOption {
  /** 选项标签 */
  label: string;
  /** 选项描述 */
  description?: string;
}

/**
 * 问题项接口
 */
interface QuestionItem {
  /** 问题文本 */
  question: string;
  /** 问题标题（可选） */
  header?: string;
  /** 选项列表（可选） */
  options?: QuestionOption[];
  /** 是否多选（可选） */
  multiSelect?: boolean;
}

// ---- 权限请求卡片 ----

/**
 * 权限卡片组件属性接口
 */
interface PermissionCardProps {
  /** 模态对话框配置 */
  modal: Record<string, unknown>;
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 响应回调函数 */
  onRespond: (requestId: string, allowed: boolean, alwaysAllow: boolean, toolName: string) => void;
}

/**
 * 权限请求卡片组件
 *
 * 显示工具执行权限请求，用户可以选择允许、拒绝或总是允许。
 *
 * @param props - 组件属性
 * @returns 返回权限卡片的 JSX 元素
 */
export function PermissionCard({ modal, lang, onRespond }: PermissionCardProps) {
  const toolName = String(modal.tool_name ?? 'tool');
  const reason = modal.reason ? String(modal.reason) : null;
  const requestId = String(modal.request_id ?? '');

  return (
    <div className="my-3 rounded-xl border border-border-light overflow-hidden shadow-soft">
      <div className="bg-surface-main px-4 py-3 flex items-center gap-2">
        <svg className="w-4 h-4 text-amber-500 shrink-0" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z" />
        </svg>
        <span className="text-sm font-medium text-content-primary">{t(lang, 'permission_request')}</span>
      </div>
      <div className="px-4 py-3">
        <div className="text-sm text-content-primary mb-1">
          {lang === 'zh-CN' ? '允许使用工具 ' : 'Allow '}
          <span className="font-mono font-medium text-primary">{toolName}</span>
          <span>?</span>
        </div>
        {reason && (
          <div className="text-xs text-content-secondary mt-1 leading-relaxed">{reason}</div>
        )}
      </div>
      <div className="px-4 py-3 border-t border-border-light flex items-center justify-end gap-2">
        <button
          onClick={() => onRespond(requestId, false, false, toolName)}
          className="px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-surface-hover rounded-md transition-colors cursor-pointer"
        >
          {t(lang, 'deny')}
        </button>
        <button
          onClick={() => onRespond(requestId, true, true, toolName)}
          className="px-3 py-1.5 text-xs font-medium text-content-primary border border-border-light hover:bg-surface-hover rounded-md transition-colors cursor-pointer"
        >
          {t(lang, 'always_allow')}
        </button>
        <button
          onClick={() => onRespond(requestId, true, false, toolName)}
          className="px-3 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer"
        >
          {t(lang, 'allow')}
        </button>
      </div>
    </div>
  );
}

// ---- 问题卡片 ----

/**
 * 问题卡片组件属性接口
 */
interface QuestionCardProps {
  /** 模态对话框配置 */
  modal: Record<string, unknown>;
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 响应回调函数 */
  onRespond: (requestId: string, answer: string) => void;
}

/**
 * 问答卡片组件
 *
 * 显示问题并支持单选、多选或自定义输入回答。
 *
 * @param props - 组件属性
 * @returns 返回问答卡片的 JSX 元素
 */
export function QuestionCard({ modal, lang, onRespond }: QuestionCardProps) {
  const requestId = String(modal.request_id ?? '');
  const questions: QuestionItem[] = Array.isArray(modal.questions) ? (modal.questions as QuestionItem[]) : [];
  const firstQuestion = questions.length > 0 ? questions[0]! : null;
  const options = firstQuestion?.options ?? [];
  const hasOptions = options.length > 0;
  const isMultiSelect = firstQuestion?.multiSelect === true && hasOptions;

  const [isCustomInput, setIsCustomInput] = useState(false);
  const [customText, setCustomText] = useState('');
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());

  useEffect(() => {
    setIsCustomInput(false);
    setCustomText('');
    setSelectedIndices(new Set());
  }, [hasOptions, options.length, isMultiSelect]);

  const handleOptionClick = useCallback(
    (idx: number, label: string) => {
      if (isMultiSelect) {
        setSelectedIndices((prev) => {
          const next = new Set(prev);
          if (next.has(idx)) next.delete(idx); else next.add(idx);
          return next;
        });
        return;
      }
      onRespond(requestId, `${idx + 1}. ${label}`);
    },
    [isMultiSelect, requestId, onRespond],
  );

  const handleMultiConfirm = useCallback(() => {
    const selected = options.filter((_, i) => selectedIndices.has(i)).map((o) => o.label);
    if (selected.length === 0) return;
    const header = firstQuestion?.header ?? 'answer';
    onRespond(requestId, JSON.stringify({ [header]: selected }));
  }, [selectedIndices, options, firstQuestion, requestId, onRespond]);

  const handleCustomSubmit = useCallback(() => {
    const text = customText.trim();
    if (!text) return;
    onRespond(requestId, text);
  }, [customText, requestId, onRespond]);

  const questionText = firstQuestion?.question ?? String(modal.question ?? 'Question');
  const hintText = isMultiSelect
    ? (lang === 'zh-CN' ? '选择所有适用项' : 'Select all that apply')
    : (lang === 'zh-CN' ? '选择一项' : 'Select one');

  return (
    <div className="my-3 rounded-xl border border-border-light overflow-hidden shadow-soft">
      <div className="bg-surface-main px-4 py-3">
        <div className="text-sm font-medium text-content-primary">{questionText}</div>
        {hasOptions && !isCustomInput && (
          <div className="text-xs text-content-disabled mt-0.5">{hintText}</div>
        )}
      </div>

      <div className="px-4 py-3">
        {typeof modal.tool_name === 'string' && modal.tool_name && (
          <div className="text-xs text-content-secondary mb-3">
            Tool: <span className="font-mono text-primary">{modal.tool_name}</span>
          </div>
        )}

        {hasOptions && !isCustomInput ? (
          <div className="space-y-1.5 mb-3">
            {options.map((opt, i) => {
              const isSelected = isMultiSelect ? selectedIndices.has(i) : false;
              return (
                <button
                  key={i}
                  onClick={() => handleOptionClick(i, opt.label)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors cursor-pointer flex items-start gap-2.5 ${
                    isSelected
                      ? 'bg-primary-light border border-primary/20'
                      : 'bg-white border border-border-light hover:bg-surface-hover'
                  }`}
                >
                  {isMultiSelect ? (
                    <span className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 text-xs transition-colors ${
                      isSelected ? 'bg-primary border-primary text-white' : 'border-border-light'
                    }`}>
                      {isSelected ? '✓' : ''}
                    </span>
                  ) : (
                    <span className="mt-0.5 w-4 h-4 rounded-full border border-border-light shrink-0 flex items-center justify-center">
                      <span className="w-2 h-2 rounded-full bg-transparent" />
                    </span>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-content-primary'}`}>{opt.label}</div>
                    {opt.description && (
                      <div className="text-xs text-content-disabled mt-0.5">{opt.description}</div>
                    )}
                  </div>
                </button>
              );
            })}
            {!isMultiSelect && (
              <button
                onClick={() => setIsCustomInput(true)}
                className="w-full text-left px-3 py-2.5 rounded-lg text-sm text-content-disabled hover:bg-surface-hover transition-colors cursor-pointer border border-border-light border-dashed"
              >
                {lang === 'zh-CN' ? '其他（手动输入）' : 'Other (type your answer)'}
              </button>
            )}
          </div>
        ) : null}

        {(isCustomInput || !hasOptions) && (
          <div className="flex gap-2 items-end">
            <textarea
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleCustomSubmit();
                }
              }}
              placeholder={lang === 'zh-CN' ? '输入你的回答...' : 'Type your answer...'}
              rows={1}
              className="flex-1 resize-none bg-white border border-border-light rounded-lg px-3 py-2 text-sm outline-none focus:border-content-disabled transition-colors"
            />
            <button
              onClick={handleCustomSubmit}
              className="px-3 py-2 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer shrink-0"
            >
              {t(lang, 'send')}
            </button>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border-light flex items-center justify-end gap-2">
        {isMultiSelect && hasOptions && (
          <button
            onClick={handleMultiConfirm}
            disabled={selectedIndices.size === 0}
            className="px-3 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {lang === 'zh-CN' ? '确认' : 'Confirm'}
          </button>
        )}
      </div>
    </div>
  );
}
