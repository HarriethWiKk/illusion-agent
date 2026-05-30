import type { UiLanguage } from '../i18n';

interface WelcomeScreenProps {
  lang: UiLanguage;
}

export default function WelcomeScreen({ lang }: WelcomeScreenProps) {
  return (
    <div className="h-full flex flex-col items-center justify-center select-text">
      {/* Logo — SVG 矢量渲染品牌名 */}
      <svg viewBox="0 0 520 60" width="480" height="56" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Illusion Code">
        <text x="260" y="46" textAnchor="middle" dominantBaseline="auto"
          fontFamily="Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"
          fontSize="48" fontWeight="700" letterSpacing="1.5" fill="#6366F1">
          Illusion Code
        </text>
      </svg>
      <p className="mt-3 text-base font-medium text-content-secondary tracking-wide">
        AI Coding Assistant
      </p>
      <div className="mt-8 flex flex-col gap-2 text-sm text-content-disabled">
        <span><span className="text-primary font-medium">/context</span> {lang === 'zh-CN' ? '管理上下文窗口' : 'manage context window'}</span>
        <span><span className="text-primary font-medium">/language</span> {lang === 'zh-CN' ? '切换语言' : 'switch language'}</span>
        <span><span className="text-primary font-medium">/compact</span> {lang === 'zh-CN' ? '压缩历史消息' : 'compact history'}</span>
      </div>
    </div>
  );
}
