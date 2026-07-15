/**
 * MarkdownRenderer — renders assistant message content as rich markdown.
 * Supports: headings, bold/italic, lists, tables, code blocks with syntax
 * highlight, blockquotes, links, task lists, strikethrough, and LaTeX
 * formulas (inline $…$ and block $$…$$) rendered via KaTeX.
 *
 * Includes a pre-processing step that normalises common LLM LaTeX output
 * variants into the $…$ / $$…$$ format that remark-math understands:
 *   \[…\]      → $$…$$   (display math)
 *   \(…\)      → $…$     (inline math)
 *   [ \cmd… ]  → $$…$$   (display math without backslash-bracket)
 *   ( \cmd… )  → $…$     (inline math — only when clearly LaTeX)
 */
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import React from "react";

interface Props {
  content: string;
}

/**
 * Converts the various LaTeX delimiter styles that LLMs commonly produce
 * into the `$…$` / `$$…$$` style that remark-math recognises.
 */
function normalizeLatex(text: string): string {
  // 1. Convert standard LaTeX block delimiters \[…\] to $$…$$
  text = text.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_m, inner) => `\n$$\n${inner.trim()}\n$$\n`);

  // 2. Convert standard LaTeX inline delimiters \(…\) to $…$
  text = text.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_m, inner) => `$${inner.trim()}$`);

  // 3. Convert display math blocks [ \cmd… ] to $$…$$
  text = text.replace(/\[\s*(\\[\s\S]*?)\s*\]/g, (_m, inner) => {
    if (/\\[a-zA-Z]/.test(inner)) {
      return `\n$$\n${inner.trim()}\n$$\n`;
    }
    return _m;
  });

  // 4. Hide all existing $$…$$ and $…$ blocks using placeholders to protect them
  const placeholders: string[] = [];
  
  // Protect $$…$$
  text = text.replace(/\$\$\s*([\s\S]*?)\s*\$\$/g, (_match, inner) => {
    placeholders.push(`$$\n${inner.trim()}\n$$`);
    return `___LATEX_PLACEHOLDER_${placeholders.length - 1}___`;
  });

  // Protect $…$
  text = text.replace(/\$\s*([^\n$]*?)\s*\$/g, (_match, inner) => {
    placeholders.push(`$${inner.trim()}$`);
    return `___LATEX_PLACEHOLDER_${placeholders.length - 1}___`;
  });

  // 5. On the remaining unprotected text, convert plain parenthesis ( math ) to $…$
  //    Only if:
  //    - The parenthese is not preceded by \left or followed by \right (lookbehinds)
  //    - It contains a backslash, operator, or is a single variable/function call to prevent text matching
  text = text.replace(/(?<!\\left)\(\s*([\s\S]*?)\s*(?<!\\right)\)/g, (match, inner) => {
    const trimmed = inner.trim();
    if (trimmed.length === 0 || trimmed.length > 150) return match;

    const isSingleVar = /^[a-zA-Z]$/.test(trimmed);
    const isFunctionCall = /^[a-zA-Z]\([a-zA-Z0-9]\)$/.test(trimmed);
    const hasMathIndicator = 
      /\\/.test(trimmed) || 
      /[+\-*/=<>]/.test(trimmed) || 
      /\b(to|implies)\b/.test(trimmed) || 
      /[_^]/.test(trimmed);

    if (isSingleVar || isFunctionCall || hasMathIndicator) {
      return `$${trimmed}$`;
    }
    return match;
  });

  // 6. Restore the protected math blocks in reverse order
  for (let i = placeholders.length - 1; i >= 0; i--) {
    text = text.replace(`___LATEX_PLACEHOLDER_${i}___`, placeholders[i]);
  }

  return text;
}

export function MarkdownRenderer({ content }: Props) {
  const normalized = normalizeLatex(content);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeHighlight, rehypeKatex, rehypeRaw]}
      components={{
        // Headings
        h1: ({ children }) => (
          <h1 className="mb-3 mt-4 text-base font-bold leading-tight first:mt-0">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="mb-2 mt-4 text-sm font-bold leading-tight first:mt-0">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="mb-1.5 mt-3 text-xs font-bold leading-snug first:mt-0">{children}</h3>
        ),
        h4: ({ children }) => (
          <h4 className="mb-1 mt-2 text-xs font-semibold leading-snug first:mt-0">{children}</h4>
        ),

        // Paragraph
        p: ({ children }) => (
          <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
        ),

        // Lists
        ul: ({ children }) => (
          <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">{children}</ol>
        ),
        li: ({ children }) => (
          <li className="leading-relaxed">{children}</li>
        ),

        // Bold / Italic
        strong: ({ children }) => (
          <strong className="font-semibold text-foreground">{children}</strong>
        ),
        em: ({ children }) => <em className="italic">{children}</em>,

        // Inline code vs fenced code block
        code: ({ className, children, ...props }) => {
          const isBlock = Boolean(className?.includes("language-") || className?.includes("math"));
          if (isBlock) {
            return (
              <code className={`${className ?? ""} text-[10.5px] leading-relaxed`} {...props}>
                {children}
              </code>
            );
          }
          return (
            <code
              className="rounded bg-muted/60 border border-border/40 px-1.5 py-0.5 font-mono text-[10.5px] text-foreground"
              {...props}
            >
              {children}
            </code>
          );
        },

        // Fenced code block wrapper
        pre: ({ children }) => (
          <pre className="mb-3 mt-1 overflow-auto rounded-lg border border-border/40 bg-muted/30 p-3 font-mono text-[10.5px] leading-relaxed scrollbar-thin last:mb-0">
            {children}
          </pre>
        ),

        // Blockquote
        blockquote: ({ children }) => (
          <blockquote className="mb-2 border-l-2 border-primary/40 pl-3 text-muted-foreground italic last:mb-0">
            {children}
          </blockquote>
        ),

        // Horizontal rule
        hr: () => <hr className="my-3 border-border/40" />,

        // Links
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:opacity-80 transition-opacity"
          >
            {children}
          </a>
        ),

        // Tables (GFM)
        table: ({ children }) => (
          <div className="mb-3 overflow-x-auto last:mb-0">
            <table className="w-full border-collapse text-[10.5px]">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="border-b border-border/50 bg-muted/30">{children}</thead>
        ),
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => (
          <tr className="border-b border-border/20 last:border-0 hover:bg-muted/10 transition-colors">
            {children}
          </tr>
        ),
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left font-semibold text-foreground">{children}</th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-muted-foreground">{children}</td>
        ),

        // Images
        img: ({ src, alt }) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={alt ?? ""}
            className="my-2 max-w-full rounded-lg border border-border/40"
          />
        ),

        // Strikethrough (GFM)
        del: ({ children }) => <del className="opacity-60">{children}</del>,

        // Checkbox list items (GFM task lists)
        input: ({ type, checked }) => {
          if (type === "checkbox") {
            return (
              <input
                type="checkbox"
                checked={checked}
                readOnly
                className="mr-1.5 accent-primary"
              />
            );
          }
          return null;
        },
      }}
    >
      {normalized}
    </ReactMarkdown>
  );
}
