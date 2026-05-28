import React from 'react';
import { t, type UiLanguage } from '../i18n';

interface WelcomeScreenProps {
  lang: UiLanguage;
}

export default function WelcomeScreen({ lang }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-4">
      <div className="w-16 h-16 border-2 border-gray-300 rounded-lg flex items-center justify-center">
        <span className="text-2xl font-bold text-gray-600">IC</span>
      </div>
      <h2 className="text-xl font-medium text-gray-700">{t(lang, 'build_anything')}</h2>
      <p className="text-sm text-gray-400">/</p>
    </div>
  );
}
