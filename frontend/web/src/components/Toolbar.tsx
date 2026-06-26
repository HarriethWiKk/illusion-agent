/**
 * @fileoverview 工具栏组件
 *
 * Web 前端的工具栏组件，提供：
 * - 权限模式切换（默认/计划/自动）
 * - 模型选择
 * - 思考强度选择
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
 * 下拉选择组件
 *
 * 通用的下拉选择器组件。
 *
 * @param props - 组件属性
 * @param props.value - 当前值
 * @param props.placeholder - 占位符文本
 * @param props.options - 选项列表
 * @param props.onChange - 变更回调
 * @param props.onOpen - 展开回调（可选）
 */
function Dropdown({ value, placeholder, options, onChange, onOpen, loading, title }: {
  value: string; placeholder?: string; options: Option[];
  onChange: (v: string) => void; onOpen?: () => void; loading?: boolean; title?: string;
}) {
  const [open, setOpen] = useState(false);
  const displayValue = value || placeholder || '-';

  return (
    <div className="relative">
      <button onClick={() => { if (!open && onOpen) onOpen(); setOpen(!open); }}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-card-alt hover:text-content-primary rounded-full transition-colors cursor-pointer border border-border-light bg-surface-main">
        {loading ? (
          <svg className="animate-spin w-3.5 h-3.5 text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <>
            <span className={!value ? 'text-content-disabled' : ''}>{displayValue}</span>
            <span className={`text-content-disabled text-[10px] transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>▾</span>
          </>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 mb-0.5 bg-surface-main border border-border-light rounded-xl shadow-lg z-20 min-w-[160px] py-1 max-h-[40vh] overflow-y-auto animate-scale-in dropdown-origin-bottom-left dropdown-scroll">
            {title && <div className="px-3 py-1.5 text-[10px] text-content-disabled font-semibold uppercase tracking-widest border-b border-border-light mb-1 text-center">{title}</div>}
            {options.map((opt, idx) => (
              <button key={opt.value} onClick={() => { onChange(opt.value); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-card-alt transition-colors cursor-pointer animate-fade-in-up ${opt.active ? 'text-primary font-medium bg-primary-light' : 'text-content-secondary'}`}
                style={{ animationDelay: `${idx * 30}ms` }}>
                {opt.label}
              </button>
            ))}
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
  // model 显示名：优先从 modelOptions 的 active 选项取 label，回退到 status.model
  const currentModelLabel = modelOptions.find((o) => o.active)?.label || currentModel;
  // 模型选项来自后端 web_models 推送，空时仅显示当前值
  const modelOpts = modelOptions.length > 0 ? modelOptions : [{ value: currentModel, label: currentModel, active: true }];

  return (
    <div className="flex items-center gap-2 px-6 py-3 border-t border-border-light bg-surface-card-alt select-none">
      <Dropdown value={currentMode} title="Mode" options={modeOptions} onChange={(v) => onSetSetting('permission_mode', v)} />
      <Dropdown value={currentModelLabel} title="Model" placeholder="Model" options={modelOpts} onChange={(v) => onSetSetting('model', v)} onOpen={onRequestModels} loading={modelSwitching} />
      <Dropdown value={currentEffort} title="Effort" placeholder={t(lang, 'effort_default')} options={effortOpts} onChange={(v) => onSetSetting('effort', v)} />
    </div>
  );
}
