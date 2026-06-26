/**
 * @fileoverview 模态卡片组件
 *
 * Web 前端的模态对话框组件，支持：
 * - 权限请求卡片（允许/拒绝/总是允许）
 * - 问答卡片（单选/多选/自定义输入）
 *
 * @module ModalCard
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  /** 禁用手动输入（可选，如沙箱权限对话框） */
  noCustomInput?: boolean;
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
    <div className="my-3 rounded-2xl glass-dropdown overflow-hidden">
      <div className="px-4 py-3 flex items-center gap-2 border-b border-border-light/40">
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
          className="px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-black/[0.03] rounded-md transition-colors cursor-pointer"
        >
          {t(lang, 'deny')}
        </button>
        <button
          onClick={() => onRespond(requestId, true, true, toolName)}
          className="px-3 py-1.5 text-xs font-medium text-content-primary border border-border-light hover:bg-black/[0.03] rounded-md transition-colors cursor-pointer"
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
  // ---- 多问题状态 ----
  const [currentIndex, setCurrentIndex] = useState(0);
  const [multiAnswers, setMultiAnswers] = useState<Record<string, string>>({});
  const isMultiQuestion = questions.length > 1;
  const currentQuestion = questions.length > 0 ? (questions[currentIndex] ?? questions[0]!) : null;
  const options = currentQuestion?.options ?? [];
  // 过滤掉LLM返回的"其他"选项，保留工具自动添加的
  const filteredOptions = useMemo(() => options.filter((opt) => {
    const lbl = opt.label.toLowerCase();
    return !(lbl === 'other' || lbl === '其他' || lbl.startsWith('other') || lbl.startsWith('其他'));
  }), [options]);
  const hasOptions = filteredOptions.length > 0;
  const isMultiSelect = currentQuestion?.multiSelect === true && hasOptions;
  const noCustomInput = currentQuestion?.noCustomInput === true;
  /** "其他"选项在 filteredOptions 之后的索引 */
  const otherIdx = filteredOptions.length;

  // 按题索引持久化多选状态（切换问题不丢失）
  const [allSelectedIndices, setAllSelectedIndices] = useState<Record<number, Set<number>>>({});
  const selectedIndices = allSelectedIndices[currentIndex] ?? new Set<number>();
  const setSelectedIndices = (updater: (prev: Set<number>) => Set<number>) => {
    setAllSelectedIndices((prev) => ({
      ...prev,
      [currentIndex]: updater(prev[currentIndex] ?? new Set<number>()),
    }));
  };
  /** "其他"选项的输入内容（按题索引持久化） */
  const [allOtherText, setAllOtherText] = useState<Record<number, string>>({});
  const otherText = allOtherText[currentIndex] ?? '';
  const setOtherText = (updater: ((prev: string) => string) | string) => {
    setAllOtherText((prev) => ({
      ...prev,
      [currentIndex]: typeof updater === 'function' ? updater(prev[currentIndex] ?? '') : updater,
    }));
  };
  /** "其他"选项是否聚焦（输入框可见） */
  const [isOtherFocused, setIsOtherFocused] = useState(false);
  const otherInputRef = useRef<HTMLInputElement>(null);
  /** 问题卡片根元素引用，用于单问题多选的失焦提交 */
  const cardRef = useRef<HTMLDivElement>(null);

  // 切换问题时恢复"其他"输入框的聚焦/显示状态：
  // 若该题已有"其他"输入内容（allOtherText 持久化），则显示输入框与选中态，
  // 否则收起。这样回到已填"其他"的问题时，界面能正确回显勾选与文本。
  useEffect(() => {
    const persistedOther = allOtherText[currentIndex]?.trim() ?? '';
    setIsOtherFocused(persistedOther.length > 0);
  }, [currentIndex, allOtherText]);

  // 单选已选答案（从 multiAnswers 回读）
  const currentHeader = currentQuestion?.header ?? `Q${currentIndex + 1}`;
  const singleSelectAnswer = !isMultiSelect && isMultiQuestion ? multiAnswers[currentHeader] : null;

  // 多选：根据当前选中集合即时计算答案。
  // - 多问题多选：选中即时写入 multiAnswers（无确认按钮，最后统一提交）
  // - 单问题多选：选中只更新本地勾选状态，待失焦时统一提交（避免选一个就被提交）
  const commitMultiSelect = useCallback(
    (selected: Set<number>) => {
      const labels = filteredOptions
        .filter((_, i) => selected.has(i))
        .map((o) => o.label);
      // 选中了"其他"且有输入内容，加入结果
      if (selected.has(otherIdx) && otherText.trim()) {
        labels.push(otherText.trim());
      }
      if (labels.length === 0) {
        // 空选：多问题下删除该 key 以保持 Submit 按钮可见性语义正确
        if (isMultiQuestion) {
          setMultiAnswers((prev) => {
            const next = { ...prev };
            delete next[currentHeader];
            return next;
          });
        }
        return;
      }
      if (isMultiQuestion) {
        // 多问题：选中即时记入，无确认按钮
        setMultiAnswers((prev) => ({ ...prev, [currentHeader]: JSON.stringify(labels) }));
      }
      // 单问题多选：不在此提交，交由卡片失焦时统一提交
    },
    [filteredOptions, otherIdx, otherText, currentHeader, isMultiQuestion],
  );

  // 单问题多选失焦提交：焦点离开问题卡片时，把当前全部选中项提交给后端
  const submitSingleMultiSelect = useCallback(() => {
    if (!isMultiSelect || isMultiQuestion) return;
    const labels = filteredOptions
      .filter((_, i) => selectedIndices.has(i))
      .map((o) => o.label);
    if (selectedIndices.has(otherIdx) && otherText.trim()) {
      labels.push(otherText.trim());
    }
    if (labels.length === 0) return;
    onRespond(requestId, JSON.stringify({ [currentHeader]: labels }));
  }, [isMultiSelect, isMultiQuestion, filteredOptions, selectedIndices, otherIdx, otherText, requestId, onRespond, currentHeader]);

  const handleOptionClick = useCallback(
    (idx: number, label: string) => {
      if (isMultiSelect) {
        if (idx === otherIdx) {
          // 多选"其他"：切换选中并聚焦输入框
          setSelectedIndices((prev) => {
            const next = new Set(prev);
            if (next.has(idx)) {
              next.delete(idx);
              setIsOtherFocused(false);
              setOtherText('');
              commitMultiSelect(next);
            } else {
              next.add(idx);
              setIsOtherFocused(true);
              setTimeout(() => otherInputRef.current?.focus(), 0);
              // 选中"其他"暂不提交——需等用户输入文本后由 handleOtherSubmit 提交
            }
            return next;
          });
          return;
        }
        setSelectedIndices((prev) => {
          const next = new Set(prev);
          if (next.has(idx)) next.delete(idx); else next.add(idx);
          // 选中即时生效
          commitMultiSelect(next);
          return next;
        });
        return;
      }
      // 单选"其他"选项：聚焦输入框
      if (idx === otherIdx) {
        setIsOtherFocused(true);
        setTimeout(() => otherInputRef.current?.focus(), 0);
        return;
      }
      // 单选提交
      if (isMultiQuestion) {
        setMultiAnswers((prev) => ({ ...prev, [currentHeader]: `${idx + 1}. ${label}` }));
      } else {
        onRespond(requestId, `${idx + 1}. ${label}`);
      }
    },
    [isMultiSelect, requestId, onRespond, otherIdx, isMultiQuestion, currentHeader, commitMultiSelect],
  );

  // 多选"其他"输入回车时提交：
  // - 单问题多选：把"其他"勾选并触发失焦式提交
  // - 多问题多选：写入 multiAnswers（统一格式）
  const handleMultiConfirm = useCallback(() => {
    if (!isMultiQuestion) {
      submitSingleMultiSelect();
    } else {
      commitMultiSelect(selectedIndices);
    }
  }, [isMultiQuestion, selectedIndices, commitMultiSelect, submitSingleMultiSelect]);

  const handleOtherSubmit = useCallback(() => {
    if (isMultiSelect) {
      handleMultiConfirm();
      return;
    }
    // 单选"其他"提交
    const text = otherText.trim();
    if (!text) return;
    if (isMultiQuestion) {
      setMultiAnswers((prev) => ({ ...prev, [currentHeader]: text }));
    } else {
      onRespond(requestId, text);
    }
  }, [isMultiSelect, otherText, handleMultiConfirm, requestId, onRespond, isMultiQuestion, currentHeader]);

  const questionText = currentQuestion?.question ?? String(modal.question ?? 'Question');
  const hintText = isMultiSelect
    ? (lang === 'zh-CN' ? '选择所有适用项' : 'Select all that apply')
    : (lang === 'zh-CN' ? '选择一项' : 'Select one');

  return (
    <div
      ref={cardRef}
      tabIndex={isMultiSelect && !isMultiQuestion ? -1 : undefined}
      onBlur={(e) => {
        // 单问题多选失焦提交：焦点离开问题卡片时提交当前全部选中项
        if (!(isMultiSelect && !isMultiQuestion)) return;
        // relatedTarget 为新聚焦元素；若它仍在卡片内，则不算失焦
        const next = e.relatedTarget as Node | null;
        if (next && cardRef.current?.contains(next)) return;
        submitSingleMultiSelect();
      }}
      className={`my-3 rounded-2xl glass-dropdown overflow-hidden ${
        isMultiSelect && !isMultiQuestion ? 'outline-none' : ''
      }`}
    >
      <div className="px-4 py-3">
        {/* Tab 导航栏 — 仅多问题时显示 */}
        {isMultiQuestion && (
          <div className="flex items-center gap-1 mb-2 overflow-x-auto">
            {questions.map((q, idx) => {
              const headerLabel = q.header ?? `Q${idx + 1}`;
              const isActive = idx === currentIndex;
              const isAnswered = headerLabel in multiAnswers;
              return (
                <button
                  key={idx}
                  onClick={() => setCurrentIndex(idx)}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors whitespace-nowrap cursor-pointer ${
                    isActive
                      ? 'bg-primary text-white'
                      : isAnswered
                        ? 'bg-primary-light text-primary border border-primary/20'
                        : 'bg-surface-hover text-content-secondary hover:bg-surface-main'
                  }`}
                >
                  {isAnswered && !isActive && <span className="mr-1">✓</span>}
                  {headerLabel}
                </button>
              );
            })}
          </div>
        )}
        <div className="text-sm font-medium text-content-primary">{questionText}</div>
        {hasOptions && (
          <div className="text-xs text-content-disabled mt-0.5">{hintText}</div>
        )}
      </div>

      <div className="px-4 py-3">
        {typeof modal.tool_name === 'string' && modal.tool_name && (
          <div className="text-xs text-content-secondary mb-3">
            Tool: <span className="font-mono text-primary">{modal.tool_name}</span>
          </div>
        )}

        {hasOptions ? (
          <div className="space-y-1.5 mb-3">
            {filteredOptions.map((opt, i) => {
              // 多选：从持久化状态读取；单选：从 multiAnswers 回读
              const isSelected = isMultiSelect
                ? selectedIndices.has(i)
                : singleSelectAnswer === `${i + 1}. ${opt.label}`;
              return (
                <button
                  key={i}
                  onClick={() => handleOptionClick(i, opt.label)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors cursor-pointer flex items-start gap-2.5 ${
                    isSelected
                      ? 'bg-black/[0.06] border border-black/[0.06]'
                      : 'border border-transparent hover:bg-black/[0.03]'
                  }`}
                >
                  {isMultiSelect ? (
                    <span className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 text-xs transition-colors ${
                      isSelected ? 'bg-primary border-primary text-white' : 'border-border-light'
                    }`}>
                      {isSelected ? '✓' : ''}
                    </span>
                  ) : (
                    <span className={`mt-0.5 w-4 h-4 rounded-full border shrink-0 flex items-center justify-center ${
                      isSelected ? 'border-primary' : 'border-border-light'
                    }`}>
                      <span className={`w-2 h-2 rounded-full ${isSelected ? 'bg-primary' : 'bg-transparent'}`} />
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
            {/* "其他"选项：内联输入框，带序号与普通选项格式一致，沙箱等 noCustomInput 场景不显示 */}
            {!noCustomInput && (
              <div
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors cursor-pointer flex items-start gap-2.5 ${
                  isMultiSelect && selectedIndices.has(otherIdx)
                    ? 'bg-black/[0.06] border border-black/[0.06]'
                    : isOtherFocused
                      ? 'bg-black/[0.04] border border-black/[0.08]'
                      : 'text-content-disabled hover:bg-black/[0.03] border border-black/[0.06] border-dashed'
                }`}
                onClick={() => handleOptionClick(otherIdx, lang === 'zh-CN' ? '其他' : 'Other')}
              >
                {isMultiSelect ? (
                  <span className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 text-xs transition-colors ${
                    selectedIndices.has(otherIdx) ? 'bg-primary border-primary text-white' : 'border-border-light'
                  }`}>
                    {selectedIndices.has(otherIdx) ? '✓' : ''}
                  </span>
                ) : (
                  <span className={`mt-0.5 w-4 h-4 rounded-full border shrink-0 flex items-center justify-center transition-colors ${
                    isOtherFocused ? 'border-primary' : 'border-border-light'
                  }`}>
                    <span className={`w-2 h-2 rounded-full transition-colors ${isOtherFocused ? 'bg-primary' : 'bg-transparent'}`} />
                  </span>
                )}
                <div className="flex-1 min-w-0 flex items-center gap-1.5">
                  <span className={`text-sm font-medium shrink-0 ${
                    (isMultiSelect && selectedIndices.has(otherIdx)) || (!isMultiSelect && isOtherFocused) ? 'text-primary' : ''
                  }`}>
                    {otherIdx + 1}. {lang === 'zh-CN' ? '其他' : 'Other'}
                  </span>{' '}
                  {isOtherFocused ? (
                    <input
                      ref={otherInputRef}
                      type="text"
                      value={otherText}
                      onChange={(e) => setOtherText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleOtherSubmit();
                        }
                        if (e.key === 'Escape') {
                          setIsOtherFocused(false);
                          setOtherText('');
                          if (isMultiSelect) {
                            setSelectedIndices((prev) => {
                              const next = new Set(prev);
                              next.delete(otherIdx);
                              return next;
                            });
                          }
                        }
                        e.stopPropagation();
                      }}
                      // 失焦自动提交：焦点离开输入框时提交已输入内容（无需回车）
                      // 注意：不限制 relatedTarget 是否在卡片内——切问题 tab 也应提交"其他"内容，
                      // 否则用户输入的文字会丢失
                      onBlur={() => {
                        handleOtherSubmit();
                      }}
                      onClick={(e) => e.stopPropagation()}
                      placeholder={lang === 'zh-CN' ? '输入后离开输入框自动提交（或按 Enter）' : 'Auto-submit on blur (or press Enter)'}
                      className="flex-1 min-w-0 bg-transparent border-none outline-none text-sm text-content-primary placeholder:text-content-disabled"
                      autoFocus
                    />
                  ) : (
                    <span className="text-sm text-content-disabled">
                      {otherText || (lang === 'zh-CN' ? '...' : '...')}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* 无选项时的输入框 */}
        {!hasOptions && (
          <div className="flex gap-2 items-end">
            <textarea
              value={otherText}
              onChange={(e) => setOtherText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  const text = otherText.trim();
                  if (!text) return;
                  if (isMultiQuestion) {
                    const header = currentQuestion?.header ?? `Q${currentIndex + 1}`;
                    setMultiAnswers((prev) => ({ ...prev, [header]: text }));
                    setOtherText('');
                  } else {
                    onRespond(requestId, text);
                  }
                }
              }}
              placeholder={lang === 'zh-CN' ? '输入你的回答...' : 'Type your answer...'}
              rows={1}
              className="flex-1 resize-none bg-white border border-border-light rounded-lg px-3 py-2 text-sm outline-none focus:border-content-disabled transition-colors"
            />
            <button
              onClick={() => {
                const text = otherText.trim();
                if (!text) return;
                if (isMultiQuestion) {
                  const header = currentQuestion?.header ?? `Q${currentIndex + 1}`;
                  setMultiAnswers((prev) => ({ ...prev, [header]: text }));
                  setOtherText('');
                } else {
                  onRespond(requestId, text);
                }
              }}
              className="px-3 py-2 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer shrink-0"
            >
              {t(lang, 'send')}
            </button>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border-light flex items-center justify-between">
        {/* 左侧：重置按钮（多问题时） */}
        <div>
          {isMultiQuestion && Object.keys(multiAnswers).length > 0 && (
            <button
              onClick={() => {
                setMultiAnswers({});
                setAllSelectedIndices({});
                setAllOtherText({});
                setCurrentIndex(0);
              }}
              className="px-3 py-1.5 text-xs font-medium text-content-secondary hover:bg-black/[0.03] rounded-md transition-colors cursor-pointer"
            >
              {lang === 'zh-CN' ? '重置' : 'Reset'}
            </button>
          )}
        </div>
        {/* 右侧：下一题 / 提交 / 确认 */}
        <div className="flex items-center gap-2">
          {isMultiQuestion && currentIndex < questions.length - 1 && (
            <button
              onClick={() => setCurrentIndex(currentIndex + 1)}
              className="px-3 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer"
            >
              {lang === 'zh-CN' ? '下一题' : 'Next'}
            </button>
          )}
          {isMultiQuestion && Object.keys(multiAnswers).length === questions.length && (
            <button
              onClick={() => {
                const result: Record<string, string | string[]> = {};
                for (const [k, v] of Object.entries(multiAnswers)) {
                  try {
                    const parsed = JSON.parse(v);
                    if (Array.isArray(parsed)) {
                      result[k] = parsed;
                    } else {
                      result[k] = v;
                    }
                  } catch {
                    result[k] = v;
                  }
                }
                onRespond(requestId, JSON.stringify(result));
              }}
              className="px-3 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer"
            >
              {lang === 'zh-CN' ? '提交' : 'Submit'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
