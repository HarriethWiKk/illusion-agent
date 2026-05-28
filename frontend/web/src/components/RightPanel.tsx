import { t, type UiLanguage } from '../i18n';

interface RightPanelProps {
  lang: UiLanguage;
  status: Record<string, unknown>;
  connected: boolean;
  busy: boolean;
  collapsed: boolean;
  onToggle: () => void;
}

export default function RightPanel({ lang, status, connected, busy, collapsed, onToggle }: RightPanelProps) {
  const mode = String(status?.permission_mode ?? 'Default');
  const cwd = String(status?.cwd ?? '-');
  const sessionId = String(status?.session_id ?? '-');
  const provider = String(status?.provider ?? '-');
  const fastMode = Boolean(status?.fast_mode);

  // 当前值从 status 读取（后端 state_payload 发送的最新值）
  const model = String(status?.model ?? '-');
  const effort = String(status?.effort ?? '');
  const effortLabel = effort ? (t(lang, `effort_${effort}`) || effort) : t(lang, 'effort_default');

  // 上下文使用量
  const contextWindow = Number(status?.context_window ?? 0);
  const contextTokens = Number(status?.context_tokens ?? 0);
  const contextPercent = contextWindow > 0 ? Math.min(100, Math.round(contextTokens * 100 / contextWindow)) : 0;

  // 折叠态：窄条 + 展开按钮
  if (collapsed) {
    return (
      <aside className="w-12 bg-surface-card border-l border-border-light flex flex-col items-center py-4 shrink-0">
        <button onClick={onToggle} title={t(lang, 'expand_panel')}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary hover:bg-surface-hover hover:text-content-primary transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 3l-5 5 5 5" />
          </svg>
        </button>
        <div className="mt-auto mb-2">
          <span className={`block w-2.5 h-2.5 rounded-full ${connected ? (busy ? 'bg-warning animate-pulse' : 'bg-success') : 'bg-danger'}`} />
        </div>
      </aside>
    );
  }

  // 展开态
  return (
    <aside className="w-[260px] bg-surface-card border-l border-border-light flex flex-col h-full shrink-0 overflow-y-auto">
      {/* 折叠按钮 */}
      <div className="px-5 pt-3 pb-1 flex justify-end">
        <button onClick={onToggle} title={t(lang, 'collapse_panel')}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-content-secondary hover:bg-surface-hover hover:text-content-primary transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 3l5 5-5 5" />
          </svg>
        </button>
      </div>

      {/* 连接状态 */}
      <div className="px-5 pb-4">
        <div className="flex items-center gap-2.5 mb-3">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${connected ? (busy ? 'bg-warning animate-pulse' : 'bg-success') : 'bg-danger'}`} />
          <span className="text-sm font-medium text-content-primary">
            {busy ? t(lang, 'thinking') : (connected ? 'Ready' : t(lang, 'disconnected'))}
          </span>
        </div>
      </div>

      {/* Model */}
      <div className="px-5 pb-4">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'model')}</div>
        <div className="text-sm text-content-primary font-medium truncate" title={model}>{model}</div>
      </div>
      <div className="mx-5 border-t border-border-light" />

      {/* Mode */}
      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'mode')}</div>
        <div className="text-sm text-content-primary">{mode}</div>
      </div>
      <div className="mx-5 border-t border-border-light" />

      {/* Effort */}
      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'effort')}</div>
        <div className="flex items-center gap-3">
          <span className={`text-sm ${effort ? 'text-content-primary' : 'text-content-disabled'}`}>{effortLabel}</span>
          <div className="flex-1 h-2 bg-surface-hover rounded-full overflow-hidden">
            <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${effortToPercent(effort)}%` }} />
          </div>
        </div>
      </div>
      <div className="mx-5 border-t border-border-light" />

      {/* Context 使用量 */}
      {contextWindow > 0 && (<>
        <div className="px-5 py-3">
          <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'context_window')}</div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-content-primary whitespace-nowrap tabular-nums">~{formatTokens(contextTokens)}/{formatTokens(contextWindow)}</span>
            <div className="flex-1 h-2 bg-surface-hover rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${contextPercent >= 95 ? 'bg-danger' : contextPercent >= 80 ? 'bg-warning' : 'bg-primary'}`}
                style={{ width: `${contextPercent}%` }}
              />
            </div>
            <span className={`text-xs font-medium tabular-nums ${contextPercent >= 95 ? 'text-danger' : contextPercent >= 80 ? 'text-warning' : 'text-content-secondary'}`}>
              {contextPercent}%
            </span>
          </div>
        </div>
        <div className="mx-5 border-t border-border-light" />
      </>)}

      {/* Provider */}
      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">Provider</div>
        <div className="text-sm text-content-primary truncate">{provider}</div>
      </div>

      {fastMode && (<>
        <div className="mx-5 border-t border-border-light" />
        <div className="px-5 py-3">
          <div className="text-xs text-content-secondary font-medium mb-1.5">Fast Mode</div>
          <div className="text-sm text-success font-medium">ON</div>
        </div>
      </>)}

      <div className="mx-5 border-t border-border-light" />
      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'cwd')}</div>
        <div className="text-xs text-content-secondary font-mono truncate" title={cwd}>{cwd}</div>
      </div>
      <div className="mx-5 border-t border-border-light" />

      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'session_info')}</div>
        <div className="text-xs text-content-secondary font-mono">{sessionId}</div>
      </div>
      <div className="flex-1" />
    </aside>
  );
}

function effortToPercent(effort: string): number {
  switch (effort) {
    case 'low': return 20; case 'medium': return 40; case 'high': return 60;
    case 'xhigh': return 80; case 'max': return 100; default: return 0;
  }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}
