import { useCallback, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

interface PromptInputProps {
  lang: UiLanguage;
  busy: boolean;
  connected: boolean;
  onSubmit: (line: string) => void;
  onStop: () => void;
}

export default function PromptInput({ lang, busy, connected, onSubmit, onStop }: PromptInputProps) {
  const [value, setValue] = useState('');

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (busy || !connected) return;
        const line = value.trim();
        if (!line) return;
        onSubmit(line);
        setValue('');
      }
    },
    [value, busy, connected, onSubmit],
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
  };

  return (
    <div className="px-4 py-3 border-t border-gray-200">
      <div className="flex items-end gap-2 bg-gray-50 rounded-lg border border-gray-300 px-3 py-2">
        <button className="text-gray-400 hover:text-gray-600 text-lg shrink-0 cursor-pointer">+</button>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={connected ? t(lang, 'input_placeholder') : t(lang, 'disconnected')}
          rows={1}
          disabled={!connected}
          className="flex-1 resize-none bg-transparent outline-none text-sm text-gray-900 placeholder-gray-400 min-h-[24px] max-h-[120px] disabled:opacity-50"
          style={{ height: 'auto', overflow: 'hidden' }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 120) + 'px';
          }}
        />
        <button
          onClick={handleSend}
          disabled={!connected && !busy}
          className={`shrink-0 w-8 h-8 flex items-center justify-center rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
            busy
              ? 'bg-red-100 text-red-500 hover:bg-red-200'
              : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
          }`}
          title={busy ? t(lang, 'task_stopped') : t(lang, 'send')}
        >
          {busy ? '■' : '↑'}
        </button>
      </div>
    </div>
  );
}
