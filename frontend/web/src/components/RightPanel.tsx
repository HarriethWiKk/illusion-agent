import { t, type UiLanguage } from '../i18n';

interface RightPanelProps {
  lang: UiLanguage;
  status: Record<string, unknown>;
  connected: boolean;
  busy: boolean;
}

export default function RightPanel({ lang, status, connected, busy }: RightPanelProps) {
  const mode = String(status?.permission_mode ?? 'Default');
  const cwd = String(status?.cwd ?? '-');
  const sessionId = String(status?.session_id ?? '-');
  const provider = String(status?.provider ?? '-');
  const fastMode = Boolean(status?.fast_mode);

  // 当前值从 status 读取（后端 state_payload 发送的最新值）
  const model = String(status?.model ?? '-');
  const effort = String(status?.effort ?? '');
  const effortLabel = effort ? (t(lang, `effort_${effort}`) || effort) : t(lang, 'effort_default');

  return (
    <aside className="w-[260px] bg-surface-card border-l border-border-light flex flex-col h-full shrink-0 overflow-y-auto">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2.5 mb-3">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${connected ? (busy ? 'bg-warning animate-pulse' : 'bg-success') : 'bg-danger'}`} />
          <span className="text-sm font-medium text-content-primary">
            {busy ? t(lang, 'thinking') : (connected ? 'Ready' : t(lang, 'disconnected'))}
          </span>
        </div>
      </div>

      <div className="px-5 pb-4">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'model')}</div>
        <div className="text-sm text-content-primary font-medium truncate" title={model}>{model}</div>
      </div>
      <div className="mx-5 border-t border-border-light" />

      <div className="px-5 py-3">
        <div className="text-xs text-content-secondary font-medium mb-1.5">{t(lang, 'mode')}</div>
        <div className="text-sm text-content-primary">{mode}</div>
      </div>
      <div className="mx-5 border-t border-border-light" />

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
