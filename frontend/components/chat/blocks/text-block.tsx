"use client";

import * as React from "react";

const LazyMarkdownRenderer = React.lazy(() =>
  import("@/components/markdown-renderer").then((m) => ({ default: m.MarkdownRenderer })),
);

interface TextBlockProps {
  content: string;
  streaming?: boolean;
}

export function TextBlock({ content, streaming }: TextBlockProps) {
  if (!content && !streaming) return null;

  return (
    <div className="select-text text-sm leading-relaxed text-foreground">
      {content ? (
        <React.Suspense
          fallback={<span className="whitespace-pre-wrap break-words">{content}</span>}
        >
          <LazyMarkdownRenderer content={content} />
        </React.Suspense>
      ) : null}
      {streaming && (
        <span className="inline-block h-4 w-1.5 ml-0.5 align-middle bg-primary animate-pulse" />
      )}
    </div>
  );
}
