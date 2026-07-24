"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";

export default function OAuthCallbackPage() {
  const params = useParams<{ provider: string }>();

  React.useEffect(() => {
    window.location.href = `/api/auth/oauth/${params.provider}/callback${window.location.search}`;
  }, [params.provider]);

  return (
    <Card glass>
      <CardContent className="p-6 text-sm text-muted-foreground">Completing OAuth sign in...</CardContent>
    </Card>
  );
}

