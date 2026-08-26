"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
    const { locale } = useTranslation();
  useEffect(() => { console.error("Unhandled error:", error); }, [error]);
  return <div className="flex min-h-[400px] items-center justify-center p-6"><div className="w-full max-w-xl"><ErrorState title={locale === "vi" ? "Something went wrong" : "Something went wrong"} description={error.message || "An unexpected error occurred while loading this page."} onRetry={reset} /></div></div>;
}
