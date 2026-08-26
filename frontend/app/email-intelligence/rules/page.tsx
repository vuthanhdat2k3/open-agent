"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RulesRedirectPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/email-intelligence?tab=rules");
  }, [router]);
  return null;
}
