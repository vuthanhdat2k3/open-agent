"use client";

import * as React from "react";
import { Globe } from "lucide-react";
import { useLanguage } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export function LanguageToggle() {
  const { locale, setLocale } = useLanguage();

  const toggle = () => {
    const next = locale === "vi" ? "en" : "vi";
    setLocale(next);
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggle}
      className="h-9 gap-1.5 px-2 text-xs font-semibold hover:bg-accent/60 active-tactile transition-transform"
      title={locale === "vi" ? "Chuyển sang Tiếng Anh (English)" : "Chuyển sang Tiếng Việt"}
      aria-label="Toggle Language"
    >
      <Globe className="h-4 w-4 text-muted-foreground" />
      <span className="font-mono uppercase tracking-wider text-[11px]">
        {locale === "vi" ? "🇻🇳 VI" : "🇬🇧 EN"}
      </span>
    </Button>
  );
}
