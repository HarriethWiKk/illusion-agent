import { t, type UiLanguage } from '../i18n';

interface WelcomeScreenProps {
  lang: UiLanguage;
}

export default function WelcomeScreen({ lang }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-content-disabled gap-6 py-20">
      <div className="w-16 h-16 border-2 border-primary/30 rounded-2xl flex items-center justify-center bg-primary-light">
        <span className="text-2xl font-display font-bold text-primary">IC</span>
      </div>
      <h2 className="text-xl font-display font-medium text-content-primary">{t(lang, 'build_anything')}</h2>
      <p className="text-sm text-content-disabled">/</p>
    </div>
  );
}
