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
  /** 思考强度选项列表 */
  effortOptions: Option[];
  /** 模型选项列表 */
  modelOptions: Option[];
  /** 权限模式变更回调 */
  onModeChange: (value: string) => void;
  /** 模型变更回调 */
  onModelChange: (value: string) => void;
  /** 思考强度变更回调 */
  onEffortChange: (value: string) => void;
  /** 请求模型列表回调 */
  onRequestModelList: () => void;
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
function Dropdown({ value, placeholder, options, onChange, onOpen }: {
  value: string; placeholder?: string; options: Option[];
  onChange: (v: string) => void; onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const displayValue = value || placeholder || '-';

  return (
    <div className="relative">
      <button onClick={() => { if (!open && onOpen) onOpen(); setOpen(!open); }}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-content-secondary hover:bg-surface-hover hover:text-content-primary rounded-lg transition-colors cursor-pointer border border-border-light bg-white">
        <span className={!value ? 'text-content-disabled' : ''}>{displayValue}</span>
        <span className="text-content-disabled text-[10px]">▾</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 mb-1 bg-white border border-border-light rounded-xl shadow-lg z-20 min-w-[160px] py-1 max-h-[40vh] overflow-y-auto">
            {options.map((opt) => (
              <button key={opt.value} onClick={() => { onChange(opt.value); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-hover transition-colors cursor-pointer ${opt.active ? 'text-primary font-medium bg-primary-light' : 'text-content-secondary'}`}>
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function Toolbar({ lang, status, effortOptions, modelOptions, onModeChange, onModelChange, onEffortChange, onRequestModelList }: ToolbarProps) {
  const modeOptions = useMemo(() => [
    { value: 'default', label: t(lang, 'mode_default') },
    { value: 'plan', label: t(lang, 'mode_plan') },
    { value: 'full_auto', label: t(lang, 'mode_auto') },
  ], [lang]);

  // 当前值从 status 读取（后端 state_payload 发送的最新值）
  const currentMode = String(status?.permission_mode ?? 'Default');
  const currentEffort = String(status?.effort ?? '');
  const currentModel = String(status?.model ?? '');
  // model 显示名：优先从 modelOptions 的 active 选项取 label，回退到 status.model
  const currentModelLabel = modelOptions.find((o) => o.active)?.label || currentModel;

  const effortOpts = effortOptions.length > 0 ? effortOptions : [
    { value: 'low', label: t(lang, 'effort_low') }, { value: 'medium', label: t(lang, 'effort_medium') },
    { value: 'high', label: t(lang, 'effort_high') }, { value: 'xhigh', label: t(lang, 'effort_xhigh') },
    { value: 'max', label: t(lang, 'effort_max') },
  ];
  const modelOpts = modelOptions.length > 0 ? modelOptions : [{ value: currentModel, label: currentModel, active: true }];

  return (
    <div className="flex items-center gap-2 px-6 py-3 border-t border-border-light bg-surface-card-alt select-none">
      <Dropdown value={currentMode} options={modeOptions} onChange={onModeChange} />
      <Dropdown value={currentModelLabel} placeholder="Model" options={modelOpts} onChange={onModelChange} onOpen={onRequestModelList} />
      <Dropdown value={currentEffort} placeholder={t(lang, 'effort_default')} options={effortOpts} onChange={onEffortChange} />
    </div>
  );
}
