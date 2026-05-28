import { t, type UiLanguage } from '../i18n';

interface RightPanelProps {
  lang: UiLanguage;
  status: Record<string, unknown>;
  connected: boolean;
  busy: boolean;
}

export default function RightPanel({ lang, status, connected, busy }: RightPanelProps) {
  const model = String(status?.model ?? '-');
  const mode = String(status?.permission_mode ?? 'Default');
  const effort = String(status?.effort ?? 'high');
  const cwd = String(status?.cwd ?? '-');
  const sessionId = String(status?.session_id ?? '-');
  const provider = String(status?.provider ?? '-');
  const fastMode = Boolean(status?.fast_mode);

  const effortLabel = t(lang, `effort_${effort}`) || effort;

  return (
    <aside className="w-[260px] bg-gradient-to-b from-cream-100/90 to-sand-100/90 backdrop-blur-sm border-l border-sand-200/60 flex flex-col h-full shrink-0 overflow-y-auto animate-slide-left">
      {/* 状态概览 */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2.5 mb-3">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${connected ? (busy ? 'bg-gradient-to-br from-cream-400 to-khaki-400 animate-pulse shadow-[0_0_8px_rgba(184,134,11,0.4)]' : 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]') : 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.4)]'}`} />
          <span className="text-sm font-medium text-khaki-700">
            {busy ? t(lang, 'thinking') : (connected ? 'Ready' : t(lang, 'disconnected'))}
          </span>
        </div>
      </div>

      {/* 模型信息 */}
      <div className="px-5 pb-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">{t(lang, 'model')}</div>
        <div className="text-sm text-khaki-700 font-medium truncate" title={model}>{model}</div>
      </div>

      <div className="mx-5 border-t border-sand-200/60" />

      {/* 模式 */}
      <div className="px-5 py-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">{t(lang, 'mode')}</div>
        <div className="text-sm text-khaki-700">{mode}</div>
      </div>

      <div className="mx-5 border-t border-sand-200/60" />

      {/* 思考强度 */}
      <div className="px-5 py-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">{t(lang, 'effort')}</div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-khaki-700">{effortLabel}</span>
          <div className="flex-1 h-2 bg-sand-200/80 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cream-400 to-khaki-400 rounded-full transition-all duration-500 shadow-sm"
              style={{ width: `${effortToPercent(effort)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mx-5 border-t border-sand-200/60" />

      {/* Provider */}
      <div className="px-5 py-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">Provider</div>
        <div className="text-sm text-khaki-700 truncate">{provider}</div>
      </div>

      {fastMode && (
        <>
          <div className="mx-5 border-t border-sand-200/60" />
          <div className="px-5 py-4">
            <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">Fast Mode</div>
            <div className="text-sm text-khaki-600 font-medium">ON</div>
          </div>
        </>
      )}

      <div className="mx-5 border-t border-sand-200/60" />

      {/* 工作目录 */}
      <div className="px-5 py-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">{t(lang, 'cwd')}</div>
        <div className="text-xs text-khaki-500 font-mono truncate" title={cwd}>{cwd}</div>
      </div>

      <div className="mx-5 border-t border-sand-200/60" />

      {/* 会话 ID */}
      <div className="px-5 py-4">
        <div className="text-[10px] uppercase tracking-[0.15em] text-khaki-400 font-semibold mb-2">{t(lang, 'session_info')}</div>
        <div className="text-xs text-khaki-500 font-mono">{sessionId}</div>
      </div>

      {/* 底部填充 */}
      <div className="flex-1" />
    </aside>
  );
}

function effortToPercent(effort: string): number {
  switch (effort) {
    case 'low': return 20;
    case 'medium': return 40;
    case 'high': return 60;
    case 'xhigh': return 80;
    case 'max': return 100;
    default: return 60;
  }
}
