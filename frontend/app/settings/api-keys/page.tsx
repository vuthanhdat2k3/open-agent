"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ApiKeysRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/settings/members?tab=keys");
  }, [router]);
  return null;
}
