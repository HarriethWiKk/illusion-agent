/**
 * @fileoverview Agent 单页创建表单组件
 *
 * Web 前端的 agent 创建表单，在 /agent create 或 /agent new 时弹出。
 * 支持双模式：
 * - generate：自然语言描述 → LLM 生成草稿 → 自动填充 name/description/system_prompt
 * - manual：直接填写空字段
 *
 * 共用字段：scope / name / description / model / system_prompt / tools / effort /
 * permission_mode / max_turns。提交时内部 identifier/when_to_use 映射为后端期望的
 * name/description（与 terminal 端 AgentWizard.tsx 第 301-319 行一致）。
 *
 * 视觉风格复用 glass-overlay / glass-surface / bg-primary 等现有类，与
 * ModalCard.tsx、CustomInputModal.tsx、BtwCard.tsx 保持一致。
 *
 * @module AgentWizardForm
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

/** 工具项类型（来自 agent_wizard_init_response.tools） */
type ToolOption = { name: string; description: string };
/** 模型项类型（来自 agent_wizard_init_response.models） */
type ModelOption = { value: string; label: string };
/** LLM 生成的 agent 草稿类型（来自 agent_generate_response.agent） */
type GeneratedAgent = { identifier: string; when_to_use: string; system_prompt: string };
/** 提交结果类型（来自 agent_wizard_result） */
type WizardResult = { success: boolean; path?: string; errors?: Record<string, string>; error?: string };

/** effort 选项值列表 */
const EFFORT_VALUES = ['low', 'medium', 'high', 'xhigh', 'max'];
/** permission_mode 选项值列表 */
const PERMISSION_VALUES = ['default', 'plan', 'full_auto'];
/** 'skip' 选项值（提交时跳过该字段） */
const SKIP_VALUE = '__skip__';
/** 'inherit' 选项值（继承默认） */
const INHERIT_VALUE = 'inherit';

/** 表单内部字段类型 */
interface FormFields {
  /** 写入范围 */
  scope: 'user' | 'project';
  /** 创建方式 */
  method: 'generate' | 'manual';
  /** agent 名称（对应后端 name） */
  identifier: string;
  /** 使用时机（对应后端 description） */
  when_to_use: string;
  /** 系统提示词 */
  system_prompt: string;
  /** 默认模型 */
  model: string;
  /** 已选工具列表 */
  tools: string[];
  /** 思考强度（'__skip__' 表示跳过） */
  effort: string;
  /** 权限模式（'__skip__' 表示跳过） */
  permission_mode: string;
  /** 最大轮次（null 表示不设置） */
  max_turns: string;
}

/** 表单初始字段 */
const INITIAL_FIELDS: FormFields = {
  scope: 'project',
  method: 'generate',
  identifier: '',
  when_to_use: '',
  system_prompt: '',
  model: INHERIT_VALUE,
  tools: [],
  effort: SKIP_VALUE,
  permission_mode: SKIP_VALUE,
  max_turns: '',
};

/** 表单字段名 → 后端字段名映射（用于清理 submissionErrors） */
const FIELD_TO_BACKEND_KEY: Record<keyof FormFields, string | null> = {
  scope: null,
  method: null,
  identifier: 'name',
  when_to_use: 'description',
  system_prompt: 'system_prompt',
  model: 'model',
  tools: 'tools',
  effort: 'effort',
  permission_mode: 'permission_mode',
  max_turns: 'max_turns',
};

/**
 * AgentWizardForm 组件属性接口
 */
interface AgentWizardFormProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 可选工具列表（来自 agent_wizard_init_response） */
  tools: ToolOption[] | null;
  /** 可选模型列表（来自 agent_wizard_init_response） */
  models: ModelOption[] | null;
  /** LLM 生成的草稿（来自 agent_generate_response） */
  generated: GeneratedAgent | null;
  /** 是否正在生成 */
  generateLoading: boolean;
  /** 生成错误文本 */
  generateError: string | null;
  /** 提交结果（来自 agent_wizard_result） */
  result: WizardResult | null;
  /** 请求初始化（拉取工具/模型列表） */
  onInit: () => void;
  /** 请求 LLM 生成草稿 */
  onGenerate: (prompt: string, model: string) => void;
  /** 提交表单 */
  onSubmit: (fields: Record<string, unknown>, scope: 'user' | 'project') => void;
  /** 关闭表单 */
  onClose: () => void;
}

/**
 * Agent 单页创建表单组件
 *
 * 显示居中玻璃拟态对话框，引导用户填写 agent 配置并提交到后端。
 * - 挂载时请求初始化工具/模型列表
 * - 收到生成草稿时自动填充 name/description/system_prompt（用户仍可二次编辑）
 * - 实时校验 name/description/system_prompt 非空
 * - 后端返回 errors 时高亮对应字段
 * - 按 Esc 键或点击右上角 × 关闭
 *
 * @param props - 组件属性
 * @returns 返回表单的 JSX 元素
 */
export function AgentWizardForm({
  lang, tools, models, generated, generateLoading, generateError, result,
  onInit, onGenerate, onSubmit, onClose,
}: AgentWizardFormProps) {
  const [fields, setFields] = useState<FormFields>(INITIAL_FIELDS);
  /** generate 模式下的描述文本 */
  const [describeText, setDescribeText] = useState('');
  /** generate 模式下的生成模型 */
  const [generateModel, setGenerateModel] = useState<string>(INHERIT_VALUE);
  /** 后端返回的字段级错误（键为后端字段名 name/description/system_prompt 等） */
  const [submissionErrors, setSubmissionErrors] = useState<Record<string, string>>({});
  /** markdown 预览是否展开 */
  const [previewExpanded, setPreviewExpanded] = useState(false);
  /** 提交中标志（点击提交后等待 agent_wizard_result 期间为 true） */
  const [submitting, setSubmitting] = useState(false);
  /** 是否已处理过当前 generated（避免重复消费） */
  const lastHandledGeneratedRef = useRef<GeneratedAgent | null>(null);
  /** 是否已处理过当前 result（避免重复消费） */
  const lastHandledResultRef = useRef<WizardResult | null>(null);

  // 挂载时请求初始化工具/模型列表
  useEffect(() => {
    onInit();
  }, [onInit]);

  // 收到生成草稿：自动填充 name/description/system_prompt（仅消费一次）
  useEffect(() => {
    if (!generated) return;
    if (generated === lastHandledGeneratedRef.current) return;
    lastHandledGeneratedRef.current = generated;
    setFields((f) => ({
      ...f,
      identifier: generated.identifier,
      when_to_use: generated.when_to_use,
      system_prompt: generated.system_prompt,
    }));
  }, [generated]);

  // 收到提交结果：清除 submitting，失败时填充字段级错误（仅消费一次）
  useEffect(() => {
    if (!result) return;
    if (result === lastHandledResultRef.current) return;
    lastHandledResultRef.current = result;
    setSubmitting(false);
    if (!result.success && result.errors) {
      setSubmissionErrors(result.errors);
    }
  }, [result]);

  // Esc 键关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  /** 更新单个字段，同时清理该字段对应的后端错误高亮 */
  const updateField = useCallback(<K extends keyof FormFields>(key: K, value: FormFields[K]) => {
    setFields((f) => ({ ...f, [key]: value }));
    const backendKey = FIELD_TO_BACKEND_KEY[key];
    if (backendKey) {
      setSubmissionErrors((prev) => {
        if (!prev[backendKey]) return prev;
        const next = { ...prev };
        delete next[backendKey];
        return next;
      });
    }
  }, []);

  /** 切换工具选中状态 */
  const toggleTool = useCallback((toolName: string) => {
    setFields((f) => {
      const has = f.tools.includes(toolName);
      return { ...f, tools: has ? f.tools.filter((t) => t !== toolName) : [...f.tools, toolName] };
    });
  }, []);

  /**
   * 触发 LLM 生成
   *
   * describeText 为空时静默忽略，避免发送空请求。
   */
  const handleGenerate = useCallback(() => {
    const s = describeText.trim();
    if (!s || generateLoading) return;
    onGenerate(s, generateModel);
  }, [describeText, generateModel, generateLoading, onGenerate]);

  /**
   * 提交完整表单
   *
   * 字段名映射：内部 identifier/when_to_use → 后端 name/description。
   * effort/permission_mode 为 '__skip__' 时省略；max_turns 为空时省略。
   */
  const handleSubmit = useCallback(() => {
    // 清空上一次的字段错误并进入 submitting 态
    setSubmissionErrors({});
    setSubmitting(true);
    // 后端 validate_agent_definition / write_agent_definition 期望字段名为
    // name / description（与 AgentDefinition frontmatter 一致）；
    // 向导内部沿用 identifier / when_to_use 是为了与 agent_generate_response
    // 返回字段保持一致，便于直接填充。提交时映射到后端期望的字段名。
    const payload: Record<string, unknown> = {
      name: fields.identifier.trim(),
      description: fields.when_to_use.trim(),
      system_prompt: fields.system_prompt,
      model: fields.model || INHERIT_VALUE,
      tools: fields.tools,
    };
    if (fields.effort !== SKIP_VALUE) payload.effort = fields.effort;
    if (fields.permission_mode !== SKIP_VALUE) payload.permission_mode = fields.permission_mode;
    const maxTurnsStr = fields.max_turns.trim();
    if (maxTurnsStr !== '') {
      const parsed = parseInt(maxTurnsStr, 10);
      if (!Number.isNaN(parsed) && parsed > 0) payload.max_turns = parsed;
    }
    onSubmit(payload, fields.scope);
  }, [fields, onSubmit]);

  /** 实时校验：name/description/system_prompt 非空 */
  const validationErrors = useMemo(() => {
    const errs: Record<string, string> = {};
    if (!fields.identifier.trim()) errs.name = t(lang, 'agentWizardNameLabel');
    if (!fields.when_to_use.trim()) errs.description = t(lang, 'agentWizardDescriptionLabel');
    if (!fields.system_prompt.trim()) errs.system_prompt = t(lang, 'agentWizardSystemPromptLabel');
    return errs;
  }, [fields.identifier, fields.when_to_use, fields.system_prompt, lang]);

  /** 是否可提交（无本地校验错误、未在提交中、未成功） */
  const canSubmit = Object.keys(validationErrors).length === 0 && !submitting && !result?.success;

  /** 生成 markdown 预览文本（frontmatter + system_prompt） */
  const markdownPreview = useMemo(() => {
    const lines: string[] = ['---'];
    if (fields.identifier.trim()) lines.push(`name: ${fields.identifier.trim()}`);
    if (fields.when_to_use.trim()) lines.push(`description: ${fields.when_to_use.trim()}`);
    lines.push(`model: ${fields.model || INHERIT_VALUE}`);
    if (fields.tools.length > 0) lines.push(`tools: [${fields.tools.join(', ')}]`);
    if (fields.effort !== SKIP_VALUE) lines.push(`effort: ${fields.effort}`);
    if (fields.permission_mode !== SKIP_VALUE) lines.push(`permission_mode: ${fields.permission_mode}`);
    const maxTurnsStr = fields.max_turns.trim();
    if (maxTurnsStr !== '') lines.push(`max_turns: ${maxTurnsStr}`);
    lines.push('---', '');
    lines.push(fields.system_prompt || '');
    return lines.join('\n');
  }, [fields]);

  /** 模型选项（含 inherit） */
  const modelOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = [{ value: INHERIT_VALUE, label: t(lang, 'agentWizardInherit') }];
    for (const m of models ?? []) opts.push({ value: m.value, label: m.label });
    return opts;
  }, [models, lang]);

  /** effort 选项（含 inherit/skip） */
  const effortOptions = useMemo(() => {
    const opts = EFFORT_VALUES.map((v) => ({ value: v, label: v }));
    opts.push({ value: INHERIT_VALUE, label: t(lang, 'agentWizardInherit') });
    opts.push({ value: SKIP_VALUE, label: t(lang, 'agentWizardSkip') });
    return opts;
  }, [lang]);

  /** permission_mode 选项（含 skip） */
  const permissionOptions = useMemo(() => {
    const opts = PERMISSION_VALUES.map((v) => ({ value: v, label: v }));
    opts.push({ value: SKIP_VALUE, label: t(lang, 'agentWizardSkip') });
    return opts;
  }, [lang]);

  /** 输入框通用样式（含错误高亮） */
  const inputClass = (hasError: boolean): string =>
    `w-full px-3 py-2 rounded-md bg-white/40 border text-content-primary text-sm focus:outline-none transition-colors ${
      hasError ? 'border-danger' : 'border-white/40 focus:border-primary'
    }`;

  /** 字段错误文案（仅显示后端返回的字段级错误；本地校验仅用于禁用提交按钮） */
  const fieldError = (key: string): string | null => submissionErrors[key] ?? null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-md animate-fade-in"
      onClick={onClose}
    >
      <div
        className="relative glass-overlay rounded-2xl w-[560px] max-w-[92vw] max-h-[88vh] flex flex-col animate-scale-in modal-origin-center"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="px-6 py-4 border-b border-border-light flex items-center justify-between shrink-0">
          <h3 className="text-lg font-semibold text-content-primary">{t(lang, 'agentWizardTitle')}</h3>
          <button
            onClick={onClose}
            title={t(lang, 'agentWizardClose')}
            className="shrink-0 w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary glass-option-hover transition-colors cursor-pointer"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M2 2l8 8M10 2l-8 8" />
            </svg>
          </button>
        </div>

        {/* 内容区（可滚动） */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* 创建方式切换 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardMethodLabel')}</div>
            <div className="flex gap-3">
              {([
                { value: 'generate', label: t(lang, 'agentWizardMethodGenerate') },
                { value: 'manual', label: t(lang, 'agentWizardMethodManual') },
              ] as const).map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-md cursor-pointer text-sm transition-colors ${
                    fields.method === opt.value
                      ? 'glass-option-active text-primary'
                      : 'glass-option-hover text-content-secondary border border-white/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="method"
                    value={opt.value}
                    checked={fields.method === opt.value}
                    onChange={() => updateField('method', opt.value)}
                    className="w-3.5 h-3.5 accent-primary"
                  />
                  <span>{opt.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* generate 模式：描述 + 模型 + 生成按钮 */}
          {fields.method === 'generate' && (
            <div className="space-y-3 p-3 rounded-lg bg-white/20 border border-white/30">
              <div>
                <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardDescribeLabel')}</div>
                <textarea
                  value={describeText}
                  onChange={(e) => setDescribeText(e.target.value)}
                  placeholder={t(lang, 'agentWizardDescribePlaceholder')}
                  rows={3}
                  className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary resize-y"
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardModelLabel')}</div>
                  <select
                    value={generateModel}
                    onChange={(e) => setGenerateModel(e.target.value)}
                    className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary"
                  >
                    {modelOptions.map((m) => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={handleGenerate}
                  disabled={generateLoading || !describeText.trim()}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                >
                  {generateLoading ? t(lang, 'agentWizardGenerating') : t(lang, 'agentWizardGenerateButton')}
                </button>
              </div>
              {generateLoading && (
                <div className="flex items-center gap-2 text-xs text-content-secondary">
                  <svg className="w-3.5 h-3.5 animate-spin text-primary" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                    <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <span>{t(lang, 'agentWizardGenerating')}</span>
                </div>
              )}
              {generateError && (
                <div className="text-xs text-danger leading-relaxed">{generateError}</div>
              )}
            </div>
          )}

          {/* 作用域 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardScopeLabel')}</div>
            <div className="flex gap-3">
              {([
                { value: 'project', label: t(lang, 'agentWizardScopeProject') },
                { value: 'user', label: t(lang, 'agentWizardScopeUser') },
              ] as const).map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-md cursor-pointer text-sm transition-colors ${
                    fields.scope === opt.value
                      ? 'glass-option-active text-primary'
                      : 'glass-option-hover text-content-secondary border border-white/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="scope"
                    value={opt.value}
                    checked={fields.scope === opt.value}
                    onChange={() => updateField('scope', opt.value)}
                    className="w-3.5 h-3.5 accent-primary"
                  />
                  <span>{opt.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* 名称 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardNameLabel')}</div>
            <input
              type="text"
              value={fields.identifier}
              onChange={(e) => updateField('identifier', e.target.value)}
              placeholder={t(lang, 'agentWizardNamePlaceholder')}
              className={inputClass(!fields.identifier.trim() || !!fieldError('name'))}
            />
            {fieldError('name') && (
              <div className="text-xs text-danger mt-1">{fieldError('name')}</div>
            )}
          </div>

          {/* 使用时机 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardDescriptionLabel')}</div>
            <input
              type="text"
              value={fields.when_to_use}
              onChange={(e) => updateField('when_to_use', e.target.value)}
              placeholder={t(lang, 'agentWizardDescriptionPlaceholder')}
              className={inputClass(!fields.when_to_use.trim() || !!fieldError('description'))}
            />
            {fieldError('description') && (
              <div className="text-xs text-danger mt-1">{fieldError('description')}</div>
            )}
          </div>

          {/* 默认模型 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardModelLabel')}</div>
            <select
              value={fields.model}
              onChange={(e) => updateField('model', e.target.value)}
              className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary"
            >
              {modelOptions.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>

          {/* 系统提示词 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardSystemPromptLabel')}</div>
            <textarea
              value={fields.system_prompt}
              onChange={(e) => updateField('system_prompt', e.target.value)}
              rows={6}
              className={`${inputClass(!fields.system_prompt.trim() || !!fieldError('system_prompt'))} resize-y font-mono`}
            />
            {fieldError('system_prompt') && (
              <div className="text-xs text-danger mt-1">{fieldError('system_prompt')}</div>
            )}
            {/* markdown 预览（可折叠） */}
            <button
              onClick={() => setPreviewExpanded((v) => !v)}
              className="mt-1.5 text-xs text-content-secondary hover:text-primary glass-option-hover rounded px-2 py-0.5 transition-colors cursor-pointer"
            >
              {previewExpanded ? '▼ ' : '▶ '}{t(lang, 'agentWizardPreview')}
            </button>
            {previewExpanded && (
              <pre className="mt-1.5 px-3 py-2 rounded-md bg-black/20 border border-white/20 text-xs text-content-secondary font-mono whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                {markdownPreview}
              </pre>
            )}
          </div>

          {/* 工具 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardToolsLabel')}</div>
            {!tools || tools.length === 0 ? (
              <div className="text-xs text-content-disabled">
                {lang === 'zh-CN' ? '暂无可用工具' : 'No tools available'}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto p-1">
                {tools.map((tool) => {
                  const checked = fields.tools.includes(tool.name);
                  return (
                    <label
                      key={tool.name}
                      title={tool.description}
                      className={`flex items-start gap-2 px-2 py-1.5 rounded-md cursor-pointer text-xs transition-colors ${
                        checked ? 'glass-option-active text-primary' : 'glass-option-hover text-content-secondary'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTool(tool.name)}
                        className="mt-0.5 w-3.5 h-3.5 accent-primary shrink-0"
                      />
                      <span className="truncate font-mono">{tool.name}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* 思考强度 / 权限模式（同一行两列） */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardEffortLabel')}</div>
              <select
                value={fields.effort}
                onChange={(e) => updateField('effort', e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary"
              >
                {effortOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardPermissionLabel')}</div>
              <select
                value={fields.permission_mode}
                onChange={(e) => updateField('permission_mode', e.target.value)}
                className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary"
              >
                {permissionOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* 最大轮次 */}
          <div>
            <div className="text-xs font-medium text-content-secondary mb-1.5">{t(lang, 'agentWizardMaxTurnsLabel')}</div>
            <input
              type="number"
              inputMode="numeric"
              min={1}
              value={fields.max_turns}
              onChange={(e) => updateField('max_turns', e.target.value)}
              placeholder={lang === 'zh-CN' ? '留空表示不设置' : 'Empty for no limit'}
              className="w-full px-3 py-2 rounded-md bg-white/40 border border-white/40 text-content-primary text-sm focus:outline-none focus:border-primary"
            />
          </div>

          {/* 提交结果 */}
          {result?.success && (
            <div className="px-3 py-2 rounded-md bg-success/10 border border-success/30 text-sm text-success">
              <div className="font-medium">{t(lang, 'agentWizardSuccess')}</div>
              {result.path && (
                <div className="text-xs text-content-secondary mt-0.5 font-mono break-all">{result.path}</div>
              )}
            </div>
          )}
          {result && !result.success && (
            <div className="px-3 py-2 rounded-md bg-danger/10 border border-danger/30 text-sm text-danger">
              <div className="font-medium">{t(lang, 'agentWizardFailed')}</div>
              {result.error && (
                <div className="text-xs mt-0.5 break-words">{result.error}</div>
              )}
            </div>
          )}
        </div>

        {/* 底部操作栏 */}
        <div className="px-6 py-4 border-t border-border-light flex items-center justify-end gap-2 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-content-secondary glass-option-hover rounded-lg transition-colors cursor-pointer border border-white/40"
          >
            {t(lang, 'agentWizardClose')}
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="px-4 py-2 text-sm text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {submitting && (
              <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeOpacity="0.4" />
                <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
            {submitting ? t(lang, 'agentWizardSubmitting') : t(lang, 'agentWizardSubmitButton')}
          </button>
        </div>
      </div>
    </div>
  );
}
