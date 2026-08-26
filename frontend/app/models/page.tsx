"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ModelsPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/providers?tab=models");
  }, [router]);
  return null;
}
