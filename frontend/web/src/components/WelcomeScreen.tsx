/**
 * @fileoverview 欢迎屏幕组件
 *
 * Web 前端的欢迎屏幕组件，在会话开始时显示。
 * 显示应用 Logo 和常用命令提示。
 *
 * 动画灵感来源：react-bits (GradientText, ShinyText, BlurText)
 *
 * @module WelcomeScreen
 */

import type { UiLanguage } from '../i18n';

/**
 * WelcomeScreen 组件属性接口
 */
interface WelcomeScreenProps {
  /** 当前 UI 语言 */
  lang: UiLanguage;
}

/**
 * 欢迎屏幕组件
 *
 * 在会话开始时显示应用 Logo 和常用命令提示。
 *
 * @param props - 组件属性
 * @returns 返回欢迎屏幕的 JSX 元素
 */
export default function WelcomeScreen({ lang }: WelcomeScreenProps) {
  return (
    <div className="h-full flex flex-col items-center justify-center select-text relative overflow-hidden">
      {/* 背景装饰：点阵网格 */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: 'radial-gradient(circle, #1a1d23 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }} />

      {/* Logo — 渐变流动文字 */}
      {/* leading-tight 而非 text-6xl 默认的 line-height:1：背景渐变（background-clip:text）
          只绘制在元素盒内，line-height:1 时 "g" 的 descender 溢出元素盒导致下半部分无背景
          （文字透明不可见），视觉上像被下方副标题截断 */}
      <h1 className="gradient-text text-7xl leading-tight font-bold tracking-tight animate-blur-in relative z-10"
        style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>
        Illusion Agent
      </h1>

      {/* 副标题 — 闪光扫过文字 */}
      <p className="mt-5 text-lg tracking-[0.3em] uppercase shiny-text animate-blur-in relative z-10"
        style={{ animationDelay: '200ms' }}>
        AI Coding Assistant
      </p>

      {/* 分割线 */}
      <div className="mt-12 w-24 h-px bg-border-medium animate-blur-in relative z-10"
        style={{ animationDelay: '350ms' }} />

      {/* 命令提示 — 模糊入场 */}
      <div className="mt-12 flex flex-col gap-4 relative z-10">
        {[
          { cmd: '/context', desc: lang === 'zh-CN' ? '管理上下文窗口' : 'manage context window', delay: 450 },
          { cmd: '/language', desc: lang === 'zh-CN' ? '切换语言' : 'switch language', delay: 550 },
          { cmd: '/compact', desc: lang === 'zh-CN' ? '压缩历史消息' : 'compact history', delay: 650 },
        ].map((item) => (
          <div key={item.cmd}
            className="animate-blur-in flex items-center gap-3"
            style={{ animationDelay: `${item.delay}ms` }}>
            <span className="text-primary font-mono font-semibold text-base">
              {item.cmd}
            </span>
            <span className="text-base text-content-disabled">
              {item.desc}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
