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
        className="flex items-center gap-1 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 rounded transition-colors cursor-pointer"
      >
        {value} <span className="text-gray-400">▾</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full left-0 mb-1 bg-white border border-gray-200 rounded-md shadow-lg z-20 min-w-[160px] py-1">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 transition-colors cursor-pointer ${
                  opt.active ? 'text-blue-600 font-medium' : 'text-gray-700'
                }`}
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
    <div className="flex items-center gap-1 px-4 py-1.5 border-t border-gray-100 bg-gray-50/50">
      <Dropdown value={currentMode} options={modeOptions} onChange={onModeChange} />
      <Dropdown value={currentModel} options={modelOptions} onChange={onModelChange} onOpen={onRequestModelList} />
      <Dropdown value={currentEffort} options={effortOptions} onChange={onEffortChange} />
    </div>
  );
}
