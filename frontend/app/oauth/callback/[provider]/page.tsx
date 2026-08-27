"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

export default function OAuthCallbackPage() {
    const { locale, tx } = useTranslation();
  const params = useParams<{ provider: string }>();

  React.useEffect(() => {
    window.location.href = `/api/auth/oauth/${params.provider}/callback${window.location.search}`;
  }, [params.provider]);

  return (
    <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
      <Card glass className="w-full shadow-3d-floating text-center border-border/80 animate-scale-in">
        <CardContent className="flex items-center justify-center gap-3 p-8 text-sm font-medium text-foreground">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          {tx("Completing OAuth sign in...", "Completing OAuth sign in...")}</CardContent>
      </Card>
    </div>
  );
}
