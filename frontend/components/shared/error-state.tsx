import * as React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function ErrorState({
  title = "Unable to load this content",
  description = "Something went wrong while loading this page.",
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <Alert variant="destructive" role="alert">
      <AlertCircle className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-3">
        <span>{description}</span>
        {onRetry && (
          <Button type="button" variant="outline" size="sm" onClick={onRetry} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
