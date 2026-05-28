import { useCallback, useEffect, useRef, useState } from 'react';
import { t, type UiLanguage } from '../i18n';

interface PromptInputProps {
  lang: UiLanguage;
  busy: boolean;
  connected: boolean;
  commands: string[];
  onSubmit: (line: string) => void;
  onStop: () => void;
}

export default function PromptInput({ lang, busy, connected, commands, onSubmit, onStop }: PromptInputProps) {
  const [value, setValue] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const filteredCommands = commands.filter((cmd) => {
    const query = value.toLowerCase();
    return cmd.toLowerCase().startsWith(query) || cmd.toLowerCase().includes(query.slice(1));
  });

  useEffect(() => {
    setSelectedIndex(0);
  }, [value]);

  useEffect(() => {
    if (showCommands && listRef.current) {
      const selected = listRef.current.children[selectedIndex] as HTMLElement;
      selected?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex, showCommands]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    setShowCommands(newValue.startsWith('/') && newValue.length > 0 && filteredCommands.length > 0);
  }, [filteredCommands.length]);

  const selectCommand = useCallback((cmd: string) => {
    setValue('');
    setShowCommands(false);
    onSubmit(`/${cmd}`);
  }, [onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (busy || !connected) return;
        const line = value.trim();
        if (!line) return;
        onSubmit(line);
        setValue('');
        setShowCommands(false);
      }
    },
    [value, busy, connected, onSubmit, showCommands, filteredCommands, selectedIndex, selectCommand],
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

  return (
    <div className="px-6 py-4 border-t border-sand-200/60 bg-gradient-to-t from-cream-100/50 to-transparent relative">
      {showCommands && filteredCommands.length > 0 && (
        <div
          ref={listRef}
          className="absolute bottom-full left-6 right-6 mb-2 bg-white/95 backdrop-blur-md border border-sand-200/80 rounded-2xl shadow-warm max-h-56 overflow-y-auto py-2 z-20 animate-slide-up"
        >
          {filteredCommands.map((cmd, idx) => (
            <button
              key={cmd}
              onClick={() => selectCommand(cmd)}
              className={`w-full text-left px-4 py-2.5 text-sm transition-all duration-200 cursor-pointer ${
                idx === selectedIndex ? 'bg-gradient-to-r from-cream-200/80 to-sand-200/80 text-khaki-800' : 'text-khaki-600 hover:bg-cream-100/80'
              }`}
            >
              <span className="font-mono">/{cmd}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-3 bg-white/90 backdrop-blur-sm rounded-2xl border border-sand-300/60 px-4 py-3 shadow-soft hover:shadow-warm transition-shadow duration-300 focus-within:shadow-warm focus-within:border-khaki-400/60">
        <textarea
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={connected ? t(lang, 'input_placeholder') : t(lang, 'disconnected')}
          rows={1}
          disabled={!connected}
          className="flex-1 resize-none bg-transparent outline-none text-base text-khaki-800 placeholder-khaki-400 min-h-[28px] max-h-[140px] disabled:opacity-50 leading-relaxed font-body"
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
          className={`shrink-0 w-10 h-10 flex items-center justify-center rounded-xl transition-all duration-200 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95 ${
            busy
              ? 'bg-gradient-to-br from-red-100 to-red-200 text-red-500 hover:from-red-200 hover:to-red-300 shadow-[0_0_12px_rgba(239,68,68,0.2)]'
              : 'bg-gradient-to-br from-cream-300 to-khaki-400 text-white hover:from-cream-400 hover:to-khaki-500 shadow-warm'
          }`}
          title={busy ? t(lang, 'task_stopped') : t(lang, 'send')}
        >
          {busy ? '■' : '↑'}
        </button>
      </div>
    </div>
  );
}
