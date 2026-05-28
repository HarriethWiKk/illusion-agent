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
    <div className="px-6 py-4 border-t border-border-light bg-surface-card-alt relative">
      {showCommands && filteredCommands.length > 0 && (
        <div
          ref={listRef}
          className="absolute bottom-full left-6 right-6 mb-1 bg-white border border-border-light rounded-xl shadow-lg max-h-56 overflow-y-auto py-1 z-20"
        >
          {filteredCommands.map((cmd, idx) => (
            <button
              key={cmd}
              onClick={() => selectCommand(cmd)}
              className={`w-full text-left px-4 py-2 text-sm transition-colors cursor-pointer ${
                idx === selectedIndex ? 'bg-primary-light text-primary' : 'text-content-secondary hover:bg-surface-hover'
              }`}
            >
              <span className="font-mono">/{cmd}</span>
            </button>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3 bg-white rounded-xl border border-border-medium px-4 py-2.5 shadow-soft focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-all">
        <textarea
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={connected ? t(lang, 'input_placeholder') : t(lang, 'disconnected')}
          rows={1}
          disabled={!connected}
          className="flex-1 resize-none bg-transparent outline-none text-base text-content-primary placeholder-content-disabled min-h-[24px] max-h-[140px] disabled:opacity-50 leading-normal py-0.5"
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
          className={`shrink-0 w-8 h-8 flex items-center justify-center rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
            busy
              ? 'bg-red-100 text-danger hover:bg-red-200'
              : 'bg-primary text-white hover:bg-primary-hover'
          }`}
          title={busy ? t(lang, 'task_stopped') : t(lang, 'send')}
        >
          {busy ? '■' : '↑'}
        </button>
      </div>
    </div>
  );
}
