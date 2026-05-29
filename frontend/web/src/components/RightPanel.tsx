import { useState } from 'react';
import { t, type UiLanguage } from '../i18n';
import TodoPanel from './TodoPanel';
import type { McpServerSnapshot, PluginSnapshot, RuleSnapshot, SkillSnapshot, TodoItemSnapshot } from '../types/protocol';

interface RightPanelProps {
  lang: UiLanguage;
  status: Record<string, unknown>;
  connected: boolean;
  busy: boolean;
  collapsed: boolean;
  onToggle: () => void;
  todoItems: TodoItemSnapshot[];
  skills: SkillSnapshot[];
  plugins: PluginSnapshot[];
  rules: RuleSnapshot[];
  mcpServers: McpServerSnapshot[];
}

export default function RightPanel({
  lang, status, connected, busy, collapsed, onToggle, todoItems,
  skills, plugins, rules, mcpServers,
}: RightPanelProps) {
  // 上下文使用量
  const contextWindow = Number(status?.context_window ?? 0);
  const contextTokens = Number(status?.context_tokens ?? 0);
  const contextPercent = contextWindow > 0 ? Math.min(100, Math.round(contextTokens * 100 / contextWindow)) : 0;

  // 折叠态
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

  // 分组统计
  const projectSkills = skills.filter((s) => s.source === 'project');
  const enabledPlugins = plugins.filter((p) => p.enabled);
  const projectRules = rules.filter((r) => r.source === 'project');

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

      {/* Todo 列表 */}
      {todoItems.length > 0 && (
        <div className="px-3 pb-3">
          <TodoPanel items={todoItems} />
        </div>
      )}

      {/* Skills */}
      {skills.length > 0 && (
        <CollapsibleSection
          title="Skills"
          count={skills.length}
          subtitle={projectSkills.length > 0 ? `${projectSkills.length} project` : undefined}
        >
          {skills.map((s) => (
            <ItemRow key={s.name} name={s.name} description={s.description} tag={s.source === 'project' ? 'P' : undefined} />
          ))}
        </CollapsibleSection>
      )}

      {/* MCP Servers */}
      {mcpServers.length > 0 && (
        <CollapsibleSection
          title="MCP"
          count={mcpServers.length}
          subtitle={mcpServers.some((s) => s.state === 'connected') ? `${mcpServers.filter((s) => s.state === 'connected').length} connected` : undefined}
        >
          {mcpServers.map((s) => (
            <ItemRow key={s.name} name={s.name} description={s.state} tag={s.tool_count != null ? `${s.tool_count}t` : undefined} />
          ))}
        </CollapsibleSection>
      )}

      {/* Plugins */}
      {plugins.length > 0 && (
        <CollapsibleSection
          title="Plugins"
          count={plugins.length}
          subtitle={enabledPlugins.length > 0 ? `${enabledPlugins.length} enabled` : undefined}
        >
          {plugins.map((p) => (
            <ItemRow key={p.name} name={p.name} description={p.description} tag={p.enabled ? undefined : 'off'} />
          ))}
        </CollapsibleSection>
      )}

      {/* Rules */}
      {rules.length > 0 && (
        <CollapsibleSection
          title="Rules"
          count={rules.length}
          subtitle={projectRules.length > 0 ? `${projectRules.length} project` : undefined}
        >
          {rules.map((r) => (
            <ItemRow key={`${r.source}-${r.name}`} name={r.name} description="" tag={r.source === 'project' ? 'P' : undefined} />
          ))}
        </CollapsibleSection>
      )}

      {/* Context 使用量 */}
      {contextWindow > 0 && (
        <div className="px-5 py-3 border-t border-border-light">
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
      )}

      <div className="flex-1" />
    </aside>
  );
}

// ---- 可折叠区域 ----

function CollapsibleSection({
  title, count, subtitle, children,
}: {
  title: string;
  count: number;
  subtitle?: string;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="border-t border-border-light">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full px-5 py-2.5 flex items-center gap-2 hover:bg-surface-hover transition-colors cursor-pointer"
      >
        <svg
          className={`w-3 h-3 text-content-disabled shrink-0 transition-transform duration-150 ${collapsed ? '' : 'rotate-90'}`}
          viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <path d="M6 3l5 5-5 5" />
        </svg>
        <span className="text-xs font-medium text-content-primary">{title}</span>
        <span className="text-xs text-content-disabled tabular-nums">{count}</span>
        {subtitle && <span className="text-xs text-content-disabled ml-auto">{subtitle}</span>}
      </button>
      {!collapsed && (
        <div className="px-5 pb-2.5 flex flex-col gap-0.5">
          {children}
        </div>
      )}
    </div>
  );
}

// ---- 单行项目 ----

function ItemRow({ name, description, tag }: { name: string; description: string; tag?: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        onClick={() => description && setExpanded((e) => !e)}
        className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors ${description ? 'hover:bg-surface-hover cursor-pointer' : 'cursor-default'}`}
      >
        <span className="text-content-primary font-medium truncate flex-1 text-left">{name}</span>
        {tag && (
          <span className="text-[10px] text-content-disabled bg-surface-main px-1.5 py-0.5 rounded shrink-0">{tag}</span>
        )}
      </button>
      {expanded && description && (
        <div className="px-2 pb-1.5 text-xs text-content-secondary leading-relaxed">{description}</div>
      )}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}
