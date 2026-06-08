import { createI18n } from 'vue-i18n';
import { messages, supportedLocales } from './messages';
import type { SupportedLocale } from './messages';

const saved = localStorage.getItem('reins_locale');
const DEFAULT_LOCALE: SupportedLocale = 'zh';

function resolveLocale(saved: string | null): SupportedLocale {
  if (saved && (supportedLocales as readonly string[]).includes(saved)) {
    return saved as SupportedLocale;
  }

  return DEFAULT_LOCALE;
}

function setHtmlLang(locale: SupportedLocale) {
  document.documentElement.lang = locale;
}

const locale = resolveLocale(saved);
setHtmlLang(locale);

export const i18n = createI18n({
  legacy: false,
  locale,
  fallbackLocale: DEFAULT_LOCALE,
  messages,
});

export function switchLocale(newLocale: string): void {
  (i18n.global.locale as any).value = newLocale;
  setHtmlLang(newLocale as SupportedLocale);
}
