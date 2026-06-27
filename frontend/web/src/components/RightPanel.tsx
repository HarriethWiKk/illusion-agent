/**
 * @fileoverview 右侧面板组件
 *
 * Web 前端的右侧面板组件，显示：
 * - 待办事项列表
 * - 技能列表
 * - MCP 服务器列表
 * - 插件列表
 * - 规则列表
 * - 上下文窗口使用量
 *
 * @module RightPanel
 */

import { useState } from 'react';
import { t, type UiLanguage } from '../i18n';
import { useTheme } from '../hooks/useTheme';
import TodoPanel from './TodoPanel';
import type { McpServerSnapshot, PluginSnapshot, RuleSnapshot, SkillSnapshot, TodoItemSnapshot } from '../types/protocol';

/**
 * RightPanel 组件属性接口
 */
interface RightPanelProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 后端状态 */
  status: Record<string, unknown>;
  /** 是否已连接 */
  connected: boolean;
  /** 是否忙碌 */
  busy: boolean;
  /** 是否折叠 */
  collapsed: boolean;
  /** 折叠/展开切换回调 */
  onToggle: () => void;
  /** 待办事项列表 */
  todoItems: TodoItemSnapshot[];
  /** 技能列表 */
  skills: SkillSnapshot[];
  /** 插件列表 */
  plugins: PluginSnapshot[];
  /** 规则列表 */
  rules: RuleSnapshot[];
  /** MCP 服务器列表 */
  mcpServers: McpServerSnapshot[];
  /** 面板宽度（可选，默认 260） */
  width?: number;
}

/**
 * 右侧面板组件
 *
 * Web 前端的右侧面板组件。
 *
 * @param props - 组件属性
 * @returns 返回右侧面板的 JSX 元素
 */
export default function RightPanel({
  lang, status, connected, busy, collapsed, onToggle, todoItems,
  skills, plugins, rules, mcpServers, width = 260,
}: RightPanelProps) {
  // 主题（深色/浅色）— 在折叠判断前调用以保证 hook 始终执行
  const { theme, toggleTheme } = useTheme();
  // 上下文使用量
  const contextWindow = Number(status?.context_window ?? 0);
  const contextTokens = Number(status?.context_tokens ?? 0);
  const contextPercent = contextWindow > 0 ? Math.min(100, Math.round(contextTokens * 100 / contextWindow)) : 0;

  // 折叠态
  if (collapsed) {
    return (
      <aside className="w-12 glass-panel border-l border-white/30 flex flex-col items-center py-4 shrink-0 select-none">
        <button onClick={onToggle} title={t(lang, 'expand_panel')}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 3l-5 5 5 5" />
          </svg>
        </button>
        <div className="mt-auto mb-2">
          <span className={`block w-2.5 h-2.5 rounded-full ${connected ? (busy ? 'bg-warning animate-pulse' : 'bg-success') : 'bg-danger'}`} style={connected && !busy ? { boxShadow: '0 0 6px rgba(76, 175, 125, 0.5)' } : busy ? { boxShadow: '0 0 6px rgba(232, 168, 76, 0.5)' } : { boxShadow: '0 0 6px rgba(212, 91, 91, 0.4)' }} />
        </div>
      </aside>
    );
  }

  // 分组统计
  const projectSkills = skills.filter((s) => s.source === 'project');
  const enabledPlugins = plugins.filter((p) => p.enabled);
  const projectRules = rules.filter((r) => r.source === 'project');

  return (
    <aside className="glass-panel border-l border-white/30 flex flex-col h-full shrink-0 overflow-y-auto select-none" style={{ width: `${width}px` }}>
      {/* 标题行：主题切换按钮 + 居中标题 + 折叠按钮（3 列 grid 严格居中） */}
      <div className="grid grid-cols-3 items-center px-5 pt-3 pb-2">
        <button onClick={toggleTheme} title={t(lang, 'toggle_theme')}
          aria-label={t(lang, 'toggle_theme')}
          className="justify-self-start w-7 h-7 flex items-center justify-center rounded-lg text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer">
          {theme === 'dark' ? (
            /* 太阳图标（深色模式下点击切换到浅色） */
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="8" cy="8" r="3" />
              <path d="M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
            </svg>
          ) : (
            /* 月亮图标（浅色模式下点击切换到深色） */
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13 8.5a5 5 0 0 1-5.5-5.5 5 5 0 1 0 5.5 5.5z" />
            </svg>
          )}
        </button>
        <span className="justify-self-center font-display font-bold text-content-primary text-sm tracking-wider">{t(lang, 'management_title')}</span>
        <button onClick={onToggle} title={t(lang, 'collapse_panel')}
          className="justify-self-end w-7 h-7 flex items-center justify-center rounded-lg text-content-secondary glass-option-hover hover:text-content-primary transition-colors cursor-pointer">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M6 3l5 5-5 5" />
          </svg>
        </button>
      </div>

      {/* Todo 列表（始终显示，空列表显示占位） */}
      <div className="px-3 pb-3">
        <TodoPanel items={todoItems} lang={lang} />
      </div>

      {/* Skills */}
      {skills.length > 0 && (
        <CollapsibleSection
          title="Skills"
          count={skills.length}
          subtitle={projectSkills.length > 0 ? `${projectSkills.length} project` : undefined}
          defaultCollapsed={false}
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
            <div className="flex-1 h-1.5 bg-black/10 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${contextPercent >= 95 ? 'bg-gradient-to-r from-warning to-danger' : contextPercent >= 80 ? 'bg-gradient-to-r from-primary to-warning' : 'bg-primary'}`}
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
  title, count, subtitle, children, defaultCollapsed = true,
}: {
  title: string;
  count: number;
  subtitle?: string;
  children: React.ReactNode;
  defaultCollapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="border-t border-border-light">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full px-5 py-2.5 flex items-center gap-2 glass-option-hover transition-colors cursor-pointer"
      >
        <svg
          className={`w-3 h-3 text-content-disabled shrink-0 transition-transform duration-200 ${collapsed ? '' : 'rotate-90'}`}
          viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <path d="M6 3l5 5-5 5" />
        </svg>
        <span className="text-xs font-semibold text-content-primary tracking-wide">{title}</span>
        <span className="text-[10px] text-content-secondary bg-[var(--badge-bg)] px-1.5 py-0.5 rounded-full tabular-nums">{count}</span>
        {subtitle && <span className="text-xs text-content-disabled ml-auto">{subtitle}</span>}
      </button>
      <div className="grid transition-[grid-template-rows] duration-200 ease-out" style={{ gridTemplateRows: collapsed ? '0fr' : '1fr' }}>
        <div className="overflow-hidden">
          <div className={`px-5 pb-2.5 flex flex-col gap-0.5 max-h-[50vh] overflow-y-auto ${collapsed ? '' : 'animate-fade-in-up'}`} style={{ animationDelay: '80ms' }}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- 单行项目 ----

function ItemRow({ name, description, tag }: { name: string; description: string; tag?: string }) {
  const [expanded, setExpanded] = useState(false);
  const hasDesc = !!description?.trim();

  return (
    <div>
      <button
        onClick={() => hasDesc && setExpanded((e) => !e)}
        className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs transition-colors ${hasDesc ? 'glass-option-hover cursor-pointer' : 'cursor-default'}`}
        title={hasDesc ? description : name}
      >
        <span className="text-content-primary font-medium truncate flex-1 text-left">{name}</span>
        {tag && (
          <span className="text-[10px] text-primary/80 bg-[var(--badge-bg)] px-1.5 py-0.5 rounded-full font-medium shrink-0">{tag}</span>
        )}
      </button>
      {expanded && hasDesc && (
        <div className="px-2 pb-1.5 text-xs text-content-secondary leading-relaxed whitespace-pre-wrap">{description}</div>
      )}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}
