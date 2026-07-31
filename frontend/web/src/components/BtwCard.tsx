/**
 * @fileoverview 侧问浮动卡片组件
 *
 * Web 前端的 btw 侧问回复展示组件，支持：
 * - 浮动卡片样式（复用 glass-surface 类）
 * - 完整 markdown 渲染（与 ModalCard 保持一致的渲染插件链）
 * - 三种状态：loading / error / reply
 * - 关闭按钮 + Esc 键关闭
 *
 * @module BtwCard
 */

import { useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkSuperscript from '../remarkSuperscript';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import { t, type UiLanguage } from '../i18n';

/**
 * BtwCard 组件属性接口
 */
interface BtwCardProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
  /** 是否加载中 */
  loading: boolean;
  /** 回复文本（成功时为非 null 字符串） */
  reply: string | null;
  /** 错误文本（失败时为非空字符串） */
  error: string | null;
  /** 关闭回调 */
  onClose: () => void;
}

/**
 * 侧问浮动卡片组件
 *
 * 显示 btw_response 的回复结果，支持 markdown 渲染与三种状态展示。
 * 按 Esc 键或点击右上角 × 关闭。
 *
 * @param props - 组件属性
 * @returns 返回侧问卡片的 JSX 元素
 */
export function BtwCard({ lang, loading, reply, error, onClose }: BtwCardProps) {
  // Esc 键关闭
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="fixed bottom-24 right-6 z-40 w-[420px] max-w-[calc(100vw-3rem)] animate-fade-in-up">
      <div className="glass-surface rounded-2xl overflow-hidden flex flex-col shadow-glow">
        {/* 标题栏 */}
        <div className="px-4 py-3 flex items-center justify-between border-b border-white/30">
          <div className="text-sm font-semibold text-content-primary">
            {t(lang, 'btw_card_title')}
          </div>
          <button
            onClick={onClose}
            title={t(lang, 'btw_close')}
            className="shrink-0 w-6 h-6 flex items-center justify-center rounded text-content-disabled hover:text-content-primary glass-option-hover transition-colors cursor-pointer"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M2 2l8 8M10 2l-8 8" />
            </svg>
          </button>
        </div>

        {/* 内容区 */}
        <div className="px-4 py-3 max-h-[70vh] overflow-y-auto">
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-content-secondary">
              <svg className="w-4 h-4 animate-spin text-primary" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span>{t(lang, 'btw_answering')}</span>
            </div>
          ) : error ? (
            <div className="text-sm text-danger leading-relaxed whitespace-pre-wrap break-words">
              {error}
            </div>
          ) : reply != null ? (
            <div className="text-sm prose prose-sm max-w-none text-content-primary select-text">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkSuperscript]}
                rehypePlugins={[rehypeHighlight, rehypeRaw]}
              >
                {reply}
              </ReactMarkdown>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
