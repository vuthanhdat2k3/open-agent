"use client";

import * as React from "react";
import type { Locale, TranslationDictionary } from "./types";
import { vi } from "./locales/vi";
import { en } from "./locales/en";

export * from "./types";

const dictionaries: Record<Locale, TranslationDictionary> = {
  vi,
  en,
};

interface LanguageContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  dict: TranslationDictionary;
  t: (path: string, defaultValue?: string) => string;
  tx: (viText: string, enText: string) => string;
}

const LanguageContext = React.createContext<LanguageContextType>({
  locale: "vi",
  setLocale: () => {},
  dict: vi,
  t: (_path: string, defaultValue?: string) => defaultValue || _path,
  tx: (viText: string) => viText,
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = React.useState<Locale>("vi");
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem("app_language") as Locale | null;
    if (saved && (saved === "vi" || saved === "en")) {
      setLocaleState(saved);
      document.documentElement.lang = saved;
    } else {
      // Auto detect user browser language
      const browserLang = navigator.language.toLowerCase().startsWith("vi") ? "vi" : "en";
      setLocaleState(browserLang);
      document.documentElement.lang = browserLang;
    }
  }, []);

  const setLocale = React.useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem("app_language", newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const dict = dictionaries[locale] || dictionaries.vi;

  const t = React.useCallback(
    (path: string, defaultValue?: string): string => {
      if (!path) return defaultValue || "";
      const segments = path.split(".");
      let curr: any = dict;
      for (const seg of segments) {
        if (curr && typeof curr === "object" && seg in curr) {
          curr = curr[seg];
        } else {
          return defaultValue !== undefined ? defaultValue : path;
        }
      }
      return typeof curr === "string" ? curr : defaultValue || path;
    },
    [dict]
  );

  const tx = React.useCallback(
    (viText: string, enText: string): string => {
      return locale === "en" ? enText : viText;
    },
    [locale]
  );

  return (
    <LanguageContext.Provider value={{ locale, setLocale, dict, t, tx }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return React.useContext(LanguageContext);
}

export function useTranslation() {
  const { t, tx, dict, locale, setLocale } = React.useContext(LanguageContext);
  return { t, tx, dict, locale, setLocale };
}
