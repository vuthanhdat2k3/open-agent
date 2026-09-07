"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
    const { locale, tx } = useTranslation();
  useEffect(() => { console.error("Unhandled error:", error); }, [error]);
  return <div className="flex min-h-[400px] items-center justify-center p-6"><div className="w-full max-w-xl"><ErrorState title={tx("Đã có lỗi xảy ra", "Something went wrong")} description={error.message || tx("Đã xảy ra lỗi ngoài mong muốn khi tải trang này.", "An unexpected error occurred while loading this page.")} onRetry={reset} /></div></div>;
}
