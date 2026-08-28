"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { useTranslation } from "@/lib/i18n";

export function LoadingSkeleton({ variant = "page" }: { variant?: "page" | "grid" | "table" }) {
  const { tx } = useTranslation();
  if (variant === "grid") {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true" aria-label={tx("Đang tải", "Loading")}>
        {Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-32 w-full" />)}
      </div>
    );
  }
  if (variant === "table") {
    return (
      <div className="space-y-2" aria-busy="true" aria-label={tx("Đang tải", "Loading")}>
        {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-11 w-full" />)}
      </div>
    );
  }
  return (
    <div className="space-y-6" aria-busy="true" aria-label={tx("Đang tải", "Loading")}>
      <div className="space-y-2"><Skeleton className="h-8 w-48" /><Skeleton className="h-4 w-96 max-w-full" /></div>
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
