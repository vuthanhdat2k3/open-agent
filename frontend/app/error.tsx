"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/shared";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error("Unhandled error:", error); }, [error]);
  return <div className="flex min-h-[400px] items-center justify-center p-6"><div className="w-full max-w-xl"><ErrorState title="Something went wrong" description={error.message || "An unexpected error occurred while loading this page."} onRetry={reset} /></div></div>;
}
