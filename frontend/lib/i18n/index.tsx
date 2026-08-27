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
  tx: (viText: string, enText: string) => viText,
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

// --- Role / Status label helpers (reused across pages) ---

const ROLE_KEY_MAP: Record<string, string> = {
  platform_admin: "roles.platformAdmin",
  platformAdmin: "roles.platformAdmin",
  org_admin: "roles.orgAdmin",
  orgAdmin: "roles.orgAdmin",
  admin: "roles.admin",
  operator: "roles.operator",
  user: "roles.user",
  assistant: "roles.assistant",
  system: "roles.system",
};

export function roleLabel(role: string | null | undefined, t: (path: string, fallback?: string) => string): string {
  if (!role) return t("roles.user", "User");
  const key = ROLE_KEY_MAP[role];
  if (!key) return role; // unknown raw role falls back to the raw value
  return t(key, role);
}

const STATUS_KEY_MAP: Record<string, string> = {
  active: "status.active",
  inactive: "status.inactive",
  enabled: "status.enabled",
  disabled: "status.disabled",
  running: "status.running",
  queued: "status.queued",
  processing: "status.processing",
  completed: "status.completed",
  succeeded: "status.completed",
  done: "status.completed",
  failed: "status.failed",
  error: "status.error",
  pending: "status.pending",
  approved: "status.approved",
  rejected: "status.rejected",
  high: "status.highRisk",
  HIGH: "status.highRisk",
  standard: "status.standard",
  STANDARD: "status.standard",
  uploaded: "status.uploaded",
  retrying: "status.retrying",
  ingested: "status.ingested",
  dead_letter: "status.deadLetter",
  deadLetter: "status.deadLetter",
  draft: "status.draft",
  published: "status.published",
  archived: "status.archived",
  unknown: "status.unknown",
  BREACHED: "status.breached",
  breached: "status.breached",
  OPEN: "status.open",
  open: "status.open",
  paused: "status.paused",
};

export function statusLabel(status: string | null | undefined, t: (path: string, fallback?: string) => string): string {
  if (!status) return t("status.unknown", "Unknown");
  const key = STATUS_KEY_MAP[status];
  if (!key) return status;
  return t(key, status);
}
