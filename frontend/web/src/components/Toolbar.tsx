/**
 * @fileoverview 工具栏组件
 *
 * Web 前端的工具栏组件，提供：
 * - 权限模式切换（默认/计划/自动）
 * - 模型选择
 * - 思考强度选择
 *
 * 该组件与输入框合并为同一张卡片，作为 PromptInput 的底部工具行注入内容，
 * 仅渲染三个下拉（不持有卡片表面、不包含发送/侧问按钮）。
 *
 * @module Toolbar
 */

import { useMemo, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

/**
 * 选项类型
 */
type Option = { value: string; label: string; active?: boolean };

/**
 * Toolbar 组件属性接口
 */
interface ToolbarProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 后端状态 */
  status: Record<string, unknown>;
  /** 模型选项列表（由后端 web_models 推送） */
  modelOptions: Option[];
  /** 统一设置变更回调（A 通道：web_set_setting） */
  onSetSetting: (key: string, value: string | number | boolean) => void;
  /** 请求模型列表回调（首次空时拉取兜底） */
  onRequestModels: () => void;
  /** 模型是否正在切换中（用于显示加载动画） */
  modelSwitching?: boolean;
}

/**
 * 后端推送的 permission_mode 为人类可读标签，映射回枚举值用于选中匹配
 */
const MODE_LABEL_TO_VALUE: Record<string, string> = {
  'Default': 'default',
  'Plan Mode': 'plan',
  'Auto': 'full_auto',
  'YOLO': 'yolo',
};

/** 权限模式枚举值集合 */
const MODE_ENUM_VALUES = ['default', 'plan', 'full_auto', 'yolo'];

/**
 * 下拉选择组件
 *
 * 通用的下拉选择器组件，选中项在右侧显示对钩。
 *
 * @param props - 组件属性
 * @param props.value - 当前显示值
 * @param props.matchValue - 用于选中匹配的值（可选，缺省回退到 value）
 * @param props.placeholder - 占位符文本
 * @param props.options - 选项列表
 * @param props.onChange - 变更回调
 * @param props.onOpen - 展开回调（可选）
 */
function Dropdown({ value, matchValue, placeholder, options, onChange, onOpen, loading, title }: {
  value: string; matchValue?: string; placeholder?: string; options: Option[];
  onChange: (v: string) => void; onOpen?: () => void; loading?: boolean; title?: string;
}) {
  const [open, setOpen] = useState(false);
  const displayValue = value || placeholder || '-';
  const match = matchValue !== undefined ? matchValue : value;
  // 选中项：优先后端标记的 active，否则按匹配值比对（大小写不敏感）
  const isActive = (opt: Option) =>
    opt.active === true || String(opt.value).toLowerCase() === String(match).toLowerCase();

  return (
    <div className="relative" onBlur={(e) => { if (!e.relatedTarget || !e.currentTarget.contains(e.relatedTarget as Node)) { setOpen(false); } }}>
      <button onClick={() => { if (!open && onOpen) onOpen(); setOpen(!open); }}
        className="pill-badge flex items-center gap-1.5 px-3 py-1.5 text-sm text-content-secondary hover:text-content-primary rounded-full cursor-pointer">
        {loading ? (
          <svg className="animate-spin w-3.5 h-3.5 text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <span className={!value ? 'text-content-disabled' : ''}>{displayValue}</span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 mb-1 glass-surface rounded-2xl z-20 min-w-[160px] py-1.5 max-h-[40vh] overflow-y-auto animate-scale-in dropdown-origin-bottom-left dropdown-scroll">
            {title && <div className="px-3 py-1.5 text-[10px] text-content-disabled font-semibold uppercase tracking-widest border-b border-border-light mb-1 text-center">{title}</div>}
            {options.map((opt, idx) => {
              const active = isActive(opt);
              return (
                <button key={opt.value} onClick={() => { onChange(opt.value); setOpen(false); }}
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-sm glass-option-hover transition-colors cursor-pointer animate-fade-in-up ${active ? 'text-primary font-medium' : 'text-content-secondary'}`}
                  style={{ animationDelay: `${idx * 30}ms` }}>
                  <span className="truncate">{opt.label}</span>
                  {active && (
                    <svg className="w-4 h-4 text-primary shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3.5 8.5l3 3 6-7" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default function Toolbar({ lang, status, modelOptions, onSetSetting, onRequestModels, modelSwitching }: ToolbarProps) {
  // 权限模式选项为前端静态常量（固定枚举，无需从后端拉取）
  const modeOptions = useMemo(() => [
    { value: 'default', label: t(lang, 'mode_default') },
    { value: 'plan', label: t(lang, 'mode_plan') },
    { value: 'full_auto', label: t(lang, 'mode_auto') },
    { value: 'yolo', label: t(lang, 'mode_yolo') },
  ], [lang]);

  // 推理强度选项为前端静态常量（固定枚举 low/medium/high/xhigh/max）
  const effortOpts = useMemo(() => [
    { value: 'low', label: t(lang, 'effort_low') },
    { value: 'medium', label: t(lang, 'effort_medium') },
    { value: 'high', label: t(lang, 'effort_high') },
    { value: 'xhigh', label: t(lang, 'effort_xhigh') },
    { value: 'max', label: t(lang, 'effort_max') },
  ], [lang]);

  // 当前值从 status 读取（后端 state_snapshot / web_setting_changed 维护的最新值）
  const currentMode = String(status?.permission_mode ?? 'Default');
  const currentEffort = String(status?.effort ?? '');
  const currentModel = String(status?.model ?? '');
  // permission_mode 为标签（如 "Auto"），映射回枚举值以匹配下拉选中
  const currentModeRaw = String(status?.permission_mode ?? 'default');
  const currentModeEnum = MODE_LABEL_TO_VALUE[currentModeRaw]
    ?? (MODE_ENUM_VALUES.includes(currentModeRaw.toLowerCase()) ? currentModeRaw.toLowerCase() : currentModeRaw);
  // model 显示名：优先从 modelOptions 的 active 选项取 label，回退到 status.model
  const currentModelLabel = modelOptions.find((o) => o.active)?.label || currentModel;
  // effort 显示名：仅首字母大写原始值（不使用 i18n，i18n 仅用于下拉选项）
  const currentEffortLabel = currentEffort
    ? currentEffort.charAt(0).toUpperCase() + currentEffort.slice(1)
    : '';
  // 模型选项来自后端 web_models 推送，空时仅显示当前值
  const modelOpts = modelOptions.length > 0 ? modelOptions : [{ value: currentModel, label: currentModel, active: true }];

  return (
    <div className="flex items-center gap-2 min-w-0 select-none">
      <Dropdown value={currentMode} matchValue={currentModeEnum} title="Mode" options={modeOptions} onChange={(v) => onSetSetting('permission_mode', v)} />
      <Dropdown value={currentModelLabel} matchValue={currentModel} title="Model" placeholder="Model" options={modelOpts} onChange={(v) => onSetSetting('model', v)} onOpen={onRequestModels} loading={modelSwitching} />
      <Dropdown value={currentEffortLabel} matchValue={currentEffort} title="Effort" placeholder={t(lang, 'effort_default')} options={effortOpts} onChange={(v) => onSetSetting('effort', v)} />
    </div>
  );
}