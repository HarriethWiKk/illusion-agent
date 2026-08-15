/**
 * @fileoverview 欢迎屏幕组件
 *
 * Web 前端的欢迎屏幕组件，在会话开始时显示。
 * 显示应用 Logo 和副标题，输入框与工具栏由上层注入到标题下方。
 *
 * 动画灵感来源：react-bits (GradientText, ShinyText, BlurText)
 *
 * @module WelcomeScreen
 */

import type { ReactNode } from 'react';

/**
 * WelcomeScreen 组件属性接口
 */
interface WelcomeScreenProps {
  /** 注入到标题下方的内容（输入框 + 工具栏卡片） */
  children?: ReactNode;
}

/**
 * 欢迎屏幕组件
 *
 * 在会话开始时显示应用 Logo 和副标题，输入框由上层注入到标题下方。
 *
 * @param props - 组件属性
 * @returns 返回欢迎屏幕的 JSX 元素
 */
export default function WelcomeScreen({ children }: WelcomeScreenProps) {
  return (
    <div className="h-full flex flex-col items-center overflow-y-auto select-text relative scrollbar-hidden">
      {/* 背景装饰：点阵网格 */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: 'radial-gradient(circle, #1a1d23 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }} />

      {/* 内容块：m-auto 垂直居中；内容超高时自动滚动且顶部可达（避免 justify-center 裁切） */}
      <div className="m-auto flex flex-col items-center w-full max-w-[var(--composer-card-max-width)] px-6 md:px-10 lg:px-16 pt-6 pb-14 relative z-10">
        {/* Logo — 渐变文字（静态，无渐入/流动动画） */}
        {/* leading-tight 而非 text-6xl 默认的 line-height:1：背景渐变（background-clip:text）
          只绘制在元素盒内，line-height:1 时 "g" 的 descender 溢出元素盒导致下半部分无背景
          （文字透明不可见），视觉上像被下方副标题截断 */}
        <h1 className="gradient-text text-6xl leading-tight font-bold tracking-tight"
          style={{ fontFamily: "'Playfair Display', Georgia, serif" }}>
          Illusion Agent
        </h1>

        {/* 副标题 — 灰度渐变文字（静态，无闪光/渐入动画，仅英文） */}
        <p className="mt-5 text-base tracking-[0.3em] uppercase shiny-text">
          Where fantasy meets functionality
        </p>

        {/* 输入框 + 工具栏（欢迎态由上层注入到标题/副标题下方） */}
        {children && (
          <div className="w-full mt-12 shrink-0">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}
