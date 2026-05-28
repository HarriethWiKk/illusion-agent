import { t, type UiLanguage } from '../i18n';

interface WelcomeScreenProps {
  lang: UiLanguage;
}

export default function WelcomeScreen({ lang }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-khaki-400 gap-6 py-20 animate-fade-in">
      <div className="relative">
        <div className="w-20 h-20 border-2 border-khaki-300/60 rounded-2xl flex items-center justify-center bg-gradient-to-br from-cream-200/80 to-sand-200/80 shadow-warm animate-float">
          <span className="text-2xl font-display font-bold text-khaki-600">IC</span>
        </div>
        <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-gradient-to-br from-cream-400 to-khaki-400 rounded-full shadow-[0_0_12px_rgba(184,134,11,0.3)] animate-pulse" />
      </div>
      <h2 className="text-xl font-display font-medium text-khaki-700">{t(lang, 'build_anything')}</h2>
      <p className="text-sm text-khaki-400">/</p>
    </div>
  );
}
