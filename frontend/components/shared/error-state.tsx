import * as React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { useTranslation } from "@/lib/i18n";

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  const { t, locale } = useTranslation();
  const defaultTitle = locale === "vi" ? "Không thể tải nội dung" : "Unable to load this content";
  const defaultDesc = locale === "vi" ? "Đã xảy ra sự cố khi tải trang này." : "Something went wrong while loading this page.";

  return (
    <Alert variant="destructive" role="alert">
      <AlertCircle className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>{title || defaultTitle}</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-3">
        <span>{description || defaultDesc}</span>
        {onRetry && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            {locale === "vi" ? "Thử lại" : "Retry"}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
