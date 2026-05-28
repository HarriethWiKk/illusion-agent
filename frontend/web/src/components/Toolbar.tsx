import { useMemo, useState } from 'react';
import { t, type UiLanguage } from '../i18n';
import type { SelectRequestPayload } from '../types/protocol';

interface ToolbarProps {
  lang: UiLanguage;
  status: Record<string, unknown>;
  selectRequest: SelectRequestPayload | null;
  onModeChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onEffortChange: (value: string) => void;
  onRequestModelList: () => void;
}

function Dropdown({
  value,
  options,
  onChange,
  onOpen,
}: {
  value: string;
  options: { value: string; label: string; active?: boolean }[];
  onChange: (v: string) => void;
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => {
          if (!open && onOpen) onOpen();
          setOpen(!open);
        }}
        className="flex items-center gap-1.5 px-3.5 py-2 text-sm text-khaki-600 hover:bg-cream-200/80 hover:text-khaki-700 rounded-xl transition-all duration-200 cursor-pointer hover:shadow-soft active:scale-[0.98]"
      >
        {value} <span className="text-khaki-400 text-[10px]">▾</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10 animate-fade-in" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 mb-2 bg-white/95 backdrop-blur-md border border-sand-200/80 rounded-2xl shadow-warm z-20 min-w-[180px] py-2 animate-scale-in">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-4 py-2.5 text-sm hover:bg-cream-100/80 transition-all duration-200 cursor-pointer rounded-lg mx-1 ${
                  opt.active ? 'text-khaki-700 font-medium bg-gradient-to-r from-cream-200/80 to-sand-200/80' : 'text-khaki-600'
                }`}
                style={{ width: 'calc(100% - 8px)' }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function Toolbar({ lang, status, selectRequest, onModeChange, onModelChange, onEffortChange, onRequestModelList }: ToolbarProps) {
  const modeOptions = useMemo(
    () => [
      { value: 'default', label: t(lang, 'mode_default') },
      { value: 'plan', label: t(lang, 'mode_plan') },
      { value: 'full_auto', label: t(lang, 'mode_auto') },
    ],
    [lang],
  );

  const effortOptions = useMemo(
    () => [
      { value: 'low', label: t(lang, 'effort_low') },
      { value: 'medium', label: t(lang, 'effort_medium') },
      { value: 'high', label: t(lang, 'effort_high') },
      { value: 'xhigh', label: t(lang, 'effort_xhigh') },
      { value: 'max', label: t(lang, 'effort_max') },
    ],
    [lang],
  );

  const currentMode = String(status?.permission_mode ?? 'Default');
  const currentEffort = String(status?.effort ?? 'high');
  const currentModel = String(status?.model ?? '');

  const modelOptions = useMemo(() => {
    if (selectRequest?.command === 'model' && selectRequest.options) {
      return selectRequest.options.map((o) => ({
        value: o.value,
        label: o.label,
        active: o.active,
      }));
    }
    return [{ value: currentModel, label: currentModel, active: true }];
  }, [selectRequest, currentModel]);

  return (
    <div className="flex items-center gap-2 px-6 py-2.5 border-t border-sand-200/60 bg-gradient-to-t from-cream-100/80 to-sand-100/50 backdrop-blur-sm">
      <Dropdown value={currentMode} options={modeOptions} onChange={onModeChange} />
      <Dropdown value={currentModel} options={modelOptions} onChange={onModelChange} onOpen={onRequestModelList} />
      <Dropdown value={currentEffort} options={effortOptions} onChange={onEffortChange} />
    </div>
  );
}
