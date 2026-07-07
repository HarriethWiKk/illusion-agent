/**
 * @fileoverview 设置弹窗组件
 *
 * Web 前端的设置弹窗，支持：
 * - onboarding 模式：首次配置 API 环境
 * - settings 模式：管理多个 API 环境（增删改查、激活）和界面语言
 *
 * @module SettingsModal
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { normalizeLanguage, t, type UiLanguage } from '../i18n';

/**
 * 环境信息接口
 */
export interface EnvInfo {
  /** 环境键名（如 env_1） */
  env_key: string;
  /** API 格式 */
  api_format: string;
  /** Base URL */
  base_url: string;
  /** 是否已配置凭证 */
  has_credential: boolean;
  /** 是否为当前激活环境 */
  active: boolean;
  /** 模型列表 */
  models: string[];
}

/**
 * SettingsModal 组件属性接口
 */
export interface SettingsModalProps {
  /** 是否打开 */
  open: boolean;
  /** 模式：onboarding（首次引导）或 settings（常规设置） */
  mode: 'onboarding' | 'settings';
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 关闭回调 */
  onClose: () => void;
  /** 环境变更通知（可选，通知父组件刷新） */
  onEnvsChanged?: () => void;
}

/** API 格式选项 */
const API_FORMATS = [
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'copilot', label: 'GitHub Copilot' },
  { value: 'codex', label: 'OpenAI Codex' },
];

/** OAuth 提供方映射：api_format → provider */
const OAUTH_PROVIDER: Record<string, 'copilot' | 'codex'> = {
  copilot: 'copilot',
  codex: 'codex',
};

/** 判断是否为 OAuth 格式（copilot/codex 走 OAuth 流程） */
function isOAuthFormat(format: string): boolean {
  return format === 'copilot' || format === 'codex';
}

/** UiLanguage → 后端语言代码（'en' → 'en-US'） */
function toBackendLang(lang: UiLanguage): string {
  return lang === 'en' ? 'en-US' : 'zh-CN';
}

/**
 * 设置弹窗组件
 *
 * 提供环境配置和界面语言切换功能。
 *
 * @param props - 组件属性
 * @returns 返回设置弹窗的 JSX 元素
 */
export default function SettingsModal({ open, mode, lang, onClose, onEnvsChanged }: SettingsModalProps) {
  const [envs, setEnvs] = useState<EnvInfo[]>([]);
  const [selectedEnvKey, setSelectedEnvKey] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // 表单状态
  const [formApiFormat, setFormApiFormat] = useState('anthropic');
  const [formBaseUrl, setFormBaseUrl] = useState('');
  const [formApiKey, setFormApiKey] = useState('');
  const [formModel1, setFormModel1] = useState('');
  const [formModel2, setFormModel2] = useState('');

  // OAuth 状态
  const [oauthStatus, setOauthStatus] = useState<'idle' | 'waiting' | 'success' | 'failed'>('idle');
  const oauthPollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // UI 语言状态（内部用 UiLanguage 类型）
  const [uiLang, setUiLang] = useState<UiLanguage>(lang);

  // 加载/错误状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 获取环境列表 */
  const fetchEnvs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/envs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEnvs(data.envs || []);
      onEnvsChanged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [onEnvsChanged]);

  // 打开时获取环境列表
  useEffect(() => {
    if (open) {
      fetchEnvs();
      setUiLang(lang);
      // onboarding 模式默认进入创建状态
      if (mode === 'onboarding') {
        setIsCreating(true);
        setSelectedEnvKey(null);
      } else {
        setIsCreating(false);
      }
    }
  }, [open, mode, lang, fetchEnvs]);

  // 选中环境时填充表单
  useEffect(() => {
    if (selectedEnvKey) {
      const env = envs.find((e) => e.env_key === selectedEnvKey);
      if (env) {
        setFormApiFormat(env.api_format || 'anthropic');
        setFormBaseUrl(env.base_url || '');
        setFormApiKey('');
        setFormModel1(env.models?.[0] || '');
        setFormModel2(env.models?.[1] || '');
      }
    } else if (!isCreating) {
      // 非创建模式且未选中环境时重置表单
      setFormApiFormat('anthropic');
      setFormBaseUrl('');
      setFormApiKey('');
      setFormModel1('');
      setFormModel2('');
    }
    setOauthStatus('idle');
  }, [selectedEnvKey, envs, isCreating]);

  // 清理 OAuth 轮询定时器
  useEffect(() => {
    return () => {
      if (oauthPollRef.current) clearTimeout(oauthPollRef.current);
    };
  }, []);

  /** 关闭弹窗时重置状态 */
  const handleClose = useCallback(() => {
    if (oauthPollRef.current) {
      clearTimeout(oauthPollRef.current);
      oauthPollRef.current = null;
    }
    setOauthStatus('idle');
    setError(null);
    onClose();
  }, [onClose]);

  /** 创建环境 */
  const handleCreateEnv = useCallback(async () => {
    setError(null);
    if (!isOAuthFormat(formApiFormat) && !formModel1.trim()) {
      setError(lang === 'zh-CN' ? '请输入模型名称' : 'Please enter model name');
      return;
    }
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        api_format: formApiFormat,
        base_url: formBaseUrl,
        api_key: formApiKey,
        // OAuth 格式使用默认模型（后端要求 model_1 必填）
        model_1: formModel1.trim() || (formApiFormat === 'copilot' ? 'gpt-4o' : 'o3'),
      };
      if (formModel2.trim()) body.model_2 = formModel2.trim();
      const res = await fetch('/api/envs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      await fetchEnvs();
      setIsCreating(false);
      if (data.env_key) setSelectedEnvKey(data.env_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [formApiFormat, formBaseUrl, formApiKey, formModel1, formModel2, lang, fetchEnvs]);

  /** 更新环境 */
  const handleUpdateEnv = useCallback(async () => {
    if (!selectedEnvKey) return;
    setError(null);
    setLoading(true);
    try {
      const env = envs.find((e) => e.env_key === selectedEnvKey);
      const addModels: Array<{ key: string; value: string }> = [];
      const removeModels: string[] = [];
      // 比较 model_1
      const origModel1 = env?.models?.[0] || '';
      if (formModel1.trim() && formModel1.trim() !== origModel1) {
        if (origModel1) removeModels.push('model_1');
        addModels.push({ key: 'model_1', value: formModel1.trim() });
      }
      // 比较 model_2
      const origModel2 = env?.models?.[1] || '';
      if (formModel2.trim() && formModel2.trim() !== origModel2) {
        if (origModel2) removeModels.push('model_2');
        addModels.push({ key: 'model_2', value: formModel2.trim() });
      }
      const body: Record<string, unknown> = {
        api_format: formApiFormat,
        base_url: formBaseUrl,
      };
      // 仅在用户输入新 api_key 时才发送（避免覆盖为空）
      if (formApiKey.trim()) body.api_key = formApiKey;
      if (addModels.length > 0) body.add_models = addModels;
      if (removeModels.length > 0) body.remove_models = removeModels;
      const res = await fetch(`/api/envs/${selectedEnvKey}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      await fetchEnvs();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedEnvKey, envs, formApiFormat, formBaseUrl, formApiKey, formModel1, formModel2, fetchEnvs]);

  /** 删除环境 */
  const handleDeleteEnv = useCallback(async (envKey: string) => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/envs/${envKey}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      if (selectedEnvKey === envKey) {
        setSelectedEnvKey(null);
      }
      await fetchEnvs();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedEnvKey, fetchEnvs]);

  /** 激活环境 */
  const handleActivateEnv = useCallback(async (envKey: string) => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`/api/envs/${envKey}/activate`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      await fetchEnvs();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [fetchEnvs]);

  /** OAuth 登录：启动 device flow 并轮询 */
  const handleOAuthLogin = useCallback(async () => {
    const provider = OAUTH_PROVIDER[formApiFormat];
    if (!provider) return;
    setError(null);
    setOauthStatus('waiting');
    try {
      // 创建模式下先创建 env（OAuth 格式需要 env 承载配置）
      if (isCreating || !selectedEnvKey) {
        const body: Record<string, unknown> = {
          api_format: formApiFormat,
          base_url: '',
          api_key: '',
          model_1: formApiFormat === 'copilot' ? 'gpt-4o' : 'o3',
        };
        const createRes = await fetch('/api/envs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!createRes.ok) {
          const err = await createRes.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${createRes.status}`);
        }
        const data = await createRes.json();
        if (data.env_key) {
          setSelectedEnvKey(data.env_key);
          setIsCreating(false);
        }
        await fetchEnvs();
      }
      // 启动 OAuth device flow
      const startRes = await fetch(`/api/oauth/${provider}/start`, { method: 'POST' });
      if (!startRes.ok) {
        const err = await startRes.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${startRes.status}`);
      }
      const startData = await startRes.json();
      const deviceCode = startData.device_code;
      // 间隔由响应 interval 字段决定，默认 5 秒
      const interval = (Number(startData.interval) || 5) * 1000;
      if (!deviceCode) throw new Error('Missing device_code');
      // 轮询 OAuth 完成状态
      const poll = async () => {
        try {
          const pollRes = await fetch(`/api/oauth/${provider}/poll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_code: deviceCode }),
          });
          if (!pollRes.ok) {
            const err = await pollRes.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${pollRes.status}`);
          }
          const pollData = await pollRes.json();
          if (pollData.success) {
            setOauthStatus('success');
            await fetchEnvs();
          } else if (pollData.error) {
            setOauthStatus('failed');
            setError(String(pollData.error));
          } else {
            // 继续轮询
            oauthPollRef.current = setTimeout(poll, interval);
          }
        } catch (e) {
          setOauthStatus('failed');
          setError(e instanceof Error ? e.message : String(e));
        }
      };
      // 首次延迟后开始轮询
      oauthPollRef.current = setTimeout(poll, interval);
    } catch (e) {
      setOauthStatus('failed');
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [formApiFormat, isCreating, selectedEnvKey, fetchEnvs]);

  /** 切换界面语言（发送后端格式 'en-US'/'zh-CN'） */
  const handleUiLangChange = useCallback(async (newLang: UiLanguage) => {
    setUiLang(newLang);
    try {
      await fetch('/api/settings/ui_language', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ui_language: toBackendLang(newLang) }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  if (!open) return null;

  const showForm = isCreating || selectedEnvKey;
  const oauthFormat = isOAuthFormat(formApiFormat);

  /** 渲染环境表单内容 */
  const renderEnvForm = () => {
    if (!showForm) {
      return (
        <div className="h-full flex items-center justify-center text-sm text-content-disabled">
          {t(lang, 'web_env_select_to_edit')}
        </div>
      );
    }
    return (
      <div className="space-y-3">
        {/* API 格式下拉 */}
        <div>
          <label className="block text-xs text-content-secondary mb-1">{t(lang, 'web_env_api_format')}</label>
          <select
            value={formApiFormat}
            onChange={(e) => { setFormApiFormat(e.target.value); setOauthStatus('idle'); }}
            className="w-full bg-white/60 border border-white/40 rounded-lg px-3 py-2 text-sm text-content-primary outline-none focus:border-primary/40 transition-colors cursor-pointer"
          >
            {API_FORMATS.map((fmt) => (
              <option key={fmt.value} value={fmt.value}>{fmt.label}</option>
            ))}
          </select>
        </div>

        {oauthFormat ? (
          /* OAuth 格式：显示登录按钮和状态 */
          <div className="space-y-3">
            {/* OAuth 登录按钮 */}
            <button
              onClick={handleOAuthLogin}
              disabled={loading || oauthStatus === 'waiting'}
              className="w-full px-4 py-2.5 text-sm font-medium text-white bg-primary hover:bg-primary-hover rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {formApiFormat === 'copilot' ? t(lang, 'web_env_oauth_login_github') : t(lang, 'web_env_oauth_login_openai')}
            </button>
            {/* OAuth 状态提示 */}
            {oauthStatus === 'waiting' && (
              <div className="flex items-center gap-2 text-xs text-content-secondary">
                <svg className="animate-spin w-3.5 h-3.5 text-primary shrink-0" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {t(lang, 'web_env_oauth_waiting')}
              </div>
            )}
            {oauthStatus === 'success' && (
              <div className="text-xs text-success">{t(lang, 'web_env_oauth_success')}</div>
            )}
            {oauthStatus === 'failed' && (
              <div className="text-xs text-danger">{t(lang, 'web_env_oauth_failed')}</div>
            )}
            {/* 已配置凭证状态 */}
            {selectedEnvKey && !isCreating && (() => {
              const env = envs.find((e) => e.env_key === selectedEnvKey);
              return env?.has_credential && oauthStatus !== 'waiting' ? (
                <div className="text-xs text-success">
                  {lang === 'zh-CN' ? '已授权' : 'Authorized'}
                </div>
              ) : null;
            })()}
          </div>
        ) : (
          /* 非 OAuth 格式：显示 base_url/api_key/model 输入框 */
          <>
            <div>
              <label className="block text-xs text-content-secondary mb-1">{t(lang, 'web_env_base_url')}</label>
              <input
                type="text"
                value={formBaseUrl}
                onChange={(e) => setFormBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1"
                className="w-full bg-white/60 border border-white/40 rounded-lg px-3 py-2 text-sm text-content-primary outline-none focus:border-primary/40 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-content-secondary mb-1">{t(lang, 'web_env_api_key')}</label>
              <input
                type="password"
                value={formApiKey}
                onChange={(e) => setFormApiKey(e.target.value)}
                placeholder={isCreating || !envs.find((e) => e.env_key === selectedEnvKey)?.has_credential ? 'sk-...' : '••••••••'}
                className="w-full bg-white/60 border border-white/40 rounded-lg px-3 py-2 text-sm text-content-primary outline-none focus:border-primary/40 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-content-secondary mb-1">{t(lang, 'web_env_model')} 1</label>
              <input
                type="text"
                value={formModel1}
                onChange={(e) => setFormModel1(e.target.value)}
                placeholder="claude-sonnet-4-5"
                className="w-full bg-white/60 border border-white/40 rounded-lg px-3 py-2 text-sm text-content-primary outline-none focus:border-primary/40 transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-content-secondary mb-1">{t(lang, 'web_env_model')} 2</label>
              <input
                type="text"
                value={formModel2}
                onChange={(e) => setFormModel2(e.target.value)}
                placeholder={lang === 'zh-CN' ? '（可选）' : '(optional)'}
                className="w-full bg-white/60 border border-white/40 rounded-lg px-3 py-2 text-sm text-content-primary outline-none focus:border-primary/40 transition-colors"
              />
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="relative glass-surface rounded-2xl border border-white/30 w-[640px] max-w-[90vw] max-h-[80vh] flex flex-col animate-scale-in modal-origin-center">
        {/* 头部 */}
        <div className="px-5 py-4 border-b border-white/30 flex items-center justify-between">
          <h3 className="text-base font-semibold text-content-primary">{t(lang, 'web_settings_title')}</h3>
          <button
            onClick={handleClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-content-secondary hover:text-content-primary glass-option-hover transition-colors cursor-pointer"
            title={t(lang, 'web_settings_close')}
          >
            <svg width="14" height="14" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M2 2l8 8M10 2l-8 8" />
            </svg>
          </button>
        </div>

        {/* onboarding 副标题 */}
        {mode === 'onboarding' && (
          <div className="px-5 py-2 text-sm text-content-secondary">{t(lang, 'web_onboarding_subtitle')}</div>
        )}

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto">
          {mode === 'settings' ? (
            <div className="flex" style={{ minHeight: '360px' }}>
              {/* 左侧：环境列表 */}
              <div className="w-48 border-r border-white/30 p-3 flex flex-col gap-1 overflow-y-auto">
                <button
                  onClick={() => { setIsCreating(true); setSelectedEnvKey(null); }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer flex items-center gap-2 ${
                    isCreating ? 'glass-option-active text-primary' : 'glass-option-hover text-content-secondary'
                  }`}
                >
                  <span className="w-5 h-5 rounded-md bg-primary flex items-center justify-center text-white font-bold text-xs">+</span>
                  {t(lang, 'web_env_add')}
                </button>
                {envs.map((env) => (
                  <div
                    key={env.env_key}
                    className={`rounded-lg transition-colors ${
                      selectedEnvKey === env.env_key && !isCreating ? 'glass-option-active' : 'glass-option-hover'
                    }`}
                  >
                    <button
                      onClick={() => { setSelectedEnvKey(env.env_key); setIsCreating(false); }}
                      className="w-full text-left px-3 py-2 text-sm text-content-primary cursor-pointer flex items-center justify-between gap-2"
                    >
                      <span className="font-mono truncate">{env.env_key}</span>
                      {env.active && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-success/20 text-success shrink-0">{t(lang, 'web_env_active')}</span>
                      )}
                    </button>
                    <div className="px-3 pb-2 flex items-center gap-1.5">
                      {!env.active && (
                        <button
                          onClick={() => handleActivateEnv(env.env_key)}
                          disabled={loading}
                          className="text-[11px] px-2 py-0.5 rounded text-primary glass-option-hover transition-colors cursor-pointer disabled:opacity-40"
                        >
                          {t(lang, 'web_env_activate')}
                        </button>
                      )}
                      {!env.active && (
                        <button
                          onClick={() => handleDeleteEnv(env.env_key)}
                          disabled={loading}
                          className="text-[11px] px-2 py-0.5 rounded text-danger glass-option-hover transition-colors cursor-pointer disabled:opacity-40"
                        >
                          {t(lang, 'web_env_delete')}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* 右侧：编辑表单 */}
              <div className="flex-1 p-4">
                {renderEnvForm()}
              </div>
            </div>
          ) : (
            /* onboarding 模式：仅显示表单 */
            <div className="p-4">
              {renderEnvForm()}
            </div>
          )}
        </div>

        {/* 底部：UI 语言选择器（仅 settings 模式） */}
        {mode === 'settings' && (
          <div className="px-5 py-3 border-t border-white/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs text-content-secondary">{t(lang, 'web_ui_language')}</span>
              <select
                value={toBackendLang(uiLang)}
                onChange={(e) => handleUiLangChange(normalizeLanguage(e.target.value))}
                className="bg-transparent border border-white/40 rounded-md px-2 py-1 text-xs text-content-primary cursor-pointer"
              >
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
            </div>
            {error && <span className="text-xs text-danger max-w-[300px] truncate">{error}</span>}
          </div>
        )}

        {/* onboarding 模式下的错误提示 */}
        {mode === 'onboarding' && error && (
          <div className="px-5 py-2 border-t border-white/30">
            <span className="text-xs text-danger">{error}</span>
          </div>
        )}

        {/* 底部按钮（仅非 OAuth 格式显示保存/取消） */}
        {showForm && !oauthFormat && (
          <div className="px-5 py-3 border-t border-white/30 flex items-center justify-end gap-2">
            <button
              onClick={handleClose}
              className="px-4 py-1.5 text-xs font-medium text-content-secondary glass-option-hover rounded-md transition-colors cursor-pointer border border-white/40"
            >
              {t(lang, 'web_settings_cancel')}
            </button>
            <button
              onClick={isCreating ? handleCreateEnv : handleUpdateEnv}
              disabled={loading}
              className="px-4 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary-hover rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {t(lang, 'web_settings_save')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
