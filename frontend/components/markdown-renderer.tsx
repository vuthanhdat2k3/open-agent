/**
 * MarkdownRenderer — renders assistant message content as rich markdown.
 * Supports: headings, bold/italic, lists, tables, code blocks with syntax
 * highlight, blockquotes, links, task lists, strikethrough, and LaTeX
 * formulas (inline $…$ and block $$…$$) rendered via KaTeX.
 *
 * Includes a pre-processing step (lib/chat/markdown-text) that normalises
 * common LLM LaTeX output variants into the $…$ / $$…$$ format that
 * remark-math understands — with guards so URLs and markdown link
 * destinations are never mangled into math.
 */
"use client";

// Scoped here rather than in the root layout: only this module renders KaTeX
// output, so the ~50KB stylesheet ships with this chunk instead of on every
// page in the app.
import "katex/dist/katex.min.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import React from "react";
import { streamSSE } from "@/lib/api";
import { inlineCodeHttpUrl, normalizeLatex } from "@/lib/chat/markdown-text";
import { useTranslation } from "@/lib/i18n";

// content is LLM output, which is attacker-influenceable via prompt
// injection (e.g. from ingested documents). rehype-raw turns raw HTML in
// markdown into real DOM nodes, so it must always be followed by
// rehype-sanitize (per rehype-raw's own docs) — never render raw HTML
// unsanitized. The schema below extends the safe default (no <script>,
// no on* handlers, href/src limited to http/https/mailto) with the
// className/style + MathML tags that rehype-highlight and rehype-katex's
// own (trusted) output needs to render correctly.
const markdownSanitizeSchema = (() => {
  const schema = JSON.parse(JSON.stringify(defaultSchema)) as typeof defaultSchema;
  schema.attributes = schema.attributes || {};
  schema.attributes["*"] = [...(schema.attributes["*"] || []), "className", "style"];
  schema.tagNames = [
    ...(schema.tagNames || []),
    "math", "semantics", "mrow", "mi", "mo", "mn", "msup", "msub", "msubsup",
    "mfrac", "msqrt", "mroot", "mtable", "mtr", "mtd", "mtext", "mspace",
    "mstyle", "mpadded", "mphantom", "menclose", "annotation",
  ];
  return schema;
})();

function extractCodeText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (typeof children === "number") return String(children);
  if (Array.isArray(children)) {
    return children.map(extractCodeText).join("");
  }
  if (React.isValidElement(children) && children.props && (children.props as any).children) {
    return extractCodeText((children.props as any).children);
  }
  return "";
}

function CodeBlockWithAction({ className, children, ...props }: any) {
    const { locale, tx } = useTranslation();
  const isBlock = Boolean(className?.includes("language-") || className?.includes("math"));
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1].toLowerCase() : "";

  const isHtml = lang === "html" || lang === "htm";
  const isRunnable = lang === "python" || lang === "bash" || lang === "sh";

  const [showPreview, setShowPreview] = React.useState(false);
  const [isRunning, setIsRunning] = React.useState(false);
  const [logs, setLogs] = React.useState<string[]>([]);
  const [exitCode, setExitCode] = React.useState<number | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const logEndRef = React.useRef<HTMLDivElement>(null);

  const codeText = React.useMemo(() => extractCodeText(children), [children]);

  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, exitCode, errorMessage]);

  if (!isBlock) {
    const plainText = extractCodeText(children);
    const linkHref = inlineCodeHttpUrl(plainText);
    if (linkHref !== undefined) {
      return (
        <code
          className="rounded bg-muted/60 border border-border/40 px-1.5 py-0.5 font-mono text-[10.5px] text-foreground"
          {...props}
        >
          <a
            href={linkHref}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline underline-offset-2 hover:opacity-80 transition-opacity"
          >
            {children}
          </a>
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
  }

  if (!isHtml && !isRunnable) {
    return (
      <code className={`${className ?? ""} text-[10.5px] leading-relaxed`} {...props}>
        {children}
      </code>
    );
  }

  const handleOpenNewTab = () => {
    const blob = new Blob([codeText], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  };

  const handleRunBackend = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setLogs([]);
    setExitCode(null);
    setErrorMessage(null);

    const targetLang = lang === "sh" ? "bash" : lang;

    try {
      await streamSSE(
        "/api/sandbox/run",
        { language: targetLang, code: codeText },
        (ev) => {
          if (ev.event === "stdout") {
            const line = ev.data?.line ?? "";
            setLogs((prev) => [...prev, line]);
          } else if (ev.event === "exit") {
            const code = ev.data?.code ?? 0;
            setExitCode(code);
          } else if (ev.event === "error") {
            setErrorMessage(ev.data?.message || tx("Lỗi thực thi", "Execution error"));
          }
        },
      );
    } catch (e: any) {
      setErrorMessage(e.message || tx("Lỗi thực thi", "Execution error"));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="relative group/code my-2">
      <div className="flex items-center justify-between px-3 py-1 bg-muted/60 border border-border/40 border-b-0 rounded-t-lg text-[10px] font-mono text-muted-foreground">
        <span className="uppercase font-semibold tracking-wider text-[9px] text-foreground/70">{lang}</span>
        {isHtml && (
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setShowPreview((v) => !v)}
              type="button"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors cursor-pointer"
            >
              {showPreview ? tx("▶ Ẩn xem trước", "▶ Hide Preview") : tx("▶ Xem trước", "▶ Preview")}
            </button>
            <button
              onClick={handleOpenNewTab}
              type="button"
              title={tx("Mở trang HTML trong tab mới", "Mở trang HTML trong tab mới")}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-muted/60 text-foreground/80 hover:bg-muted transition-colors cursor-pointer"
            >
              {tx("↗ Mở tab mới", "↗ Mở tab mới")}</button>
          </div>
        )}
        {isRunnable && (
          <button
            onClick={handleRunBackend}
            disabled={isRunning}
            type="button"
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[10px] font-medium bg-success/15 text-success hover:bg-success/25 border border-success/30 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {isRunning ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-success animate-ping" />
                {tx("Running...", "Running...")}</>
            ) : (
              tx("▶ Chạy", "▶ Run")
            )}
          </button>
        )}
      </div>

      <code className={`${className ?? ""} text-[10.5px] leading-relaxed block border border-border/40 border-t-0 rounded-b-lg bg-muted/30 p-3 overflow-x-auto`} {...props}>
        {children}
      </code>

      {isHtml && showPreview && (
        <div className="mt-2 rounded-lg border border-border/60 overflow-hidden bg-white dark:bg-card">
          <div className="bg-muted/40 px-3 py-1 text-[10px] font-mono text-muted-foreground border-b border-border/40 flex items-center justify-between">
            <span>{tx("HTML Sandbox Preview", "HTML Sandbox Preview")}</span>
            <span className="text-[9px] opacity-70">{tx("iframe sandbox=&quot;allow-scripts&quot;", "iframe sandbox=&quot;allow-scripts&quot;")}</span>
          </div>
          <iframe
            srcDoc={codeText}
            sandbox="allow-scripts"
            className="w-full h-64 border-0 bg-white"
            title={tx("HTML Preview", "HTML Preview")}
          />
        </div>
      )}

      {isRunnable && (logs.length > 0 || exitCode !== null || errorMessage !== null || isRunning) && (
              <div className="mt-2 rounded-lg border border-border/60 bg-background/95 overflow-hidden font-mono text-[10.5px] text-foreground shadow-card">
          <div className="bg-muted/40 px-3 py-1 text-[10px] text-muted-foreground border-b border-border/40 flex items-center justify-between">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${isRunning ? "bg-warning animate-pulse" : exitCode === 0 ? "bg-success" : "bg-destructive"}`} />
              {tx("Output Console", "Output Console")}</span>
            {exitCode !== null && (
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${exitCode === 0 ? "bg-success/20 text-success" : "bg-destructive/20 text-destructive"}`}>
                {tx("exit code:", "exit code:")}{exitCode}
              </span>
            )}
          </div>
          <pre className="p-3 max-h-60 overflow-y-auto whitespace-pre-wrap break-all leading-relaxed scrollbar-thin text-zinc-100">
            {logs.map((l, i) => (
              <span key={i}>{l}</span>
            ))}
            {errorMessage && (
              <span className="text-destructive block font-semibold">{errorMessage}</span>
            )}
            {exitCode !== null && (
              <span className={`block font-bold mt-1.5 pt-1.5 border-t border-white/10 ${exitCode === 0 ? "text-success" : "text-destructive"}`}>
                {tx("[exit code:", "[exit code:")}{exitCode}]
              </span>
            )}
            <div ref={logEndRef} />
          </pre>
        </div>
      )}
    </div>
  );
}

interface Props {
  content: string;
}

function MarkdownRendererBase({ content }: Props) {
    const { locale, tx } = useTranslation();
  const normalized = React.useMemo(() => normalizeLatex(content), [content]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeHighlight, rehypeKatex, rehypeRaw, [rehypeSanitize, markdownSanitizeSchema]]}
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

        // Inline code vs fenced code block with Run / Preview action
        code: (props) => <CodeBlockWithAction {...props} />,

        // Fenced code block wrapper
        pre: ({ children }) => (
          <div className="mb-3 mt-1 overflow-x-auto rounded-lg border border-border/40 bg-muted/30 font-mono text-[10.5px] leading-relaxed scrollbar-thin last:mb-0">
            {children}
          </div>
        ),

        // Blockquote
        blockquote: ({ children }) => (
          <blockquote className="mb-2 border-l-2 border-primary/40 pl-3 text-muted-foreground italic last:mb-0">
            {children}
          </blockquote>
        ),

        // Horizontal rule
        hr: () => <hr className="my-3 border-border/40" />,

        // Links — rehype-sanitize's schema already strips non-http(s)/mailto
        // hrefs, but check again here so a schema regression can't silently
        // reintroduce a javascript: URL click-to-XSS.
        a: ({ href, children }) => {
          const safeHref =
            href && /^(https?:|mailto:)/i.test(href) ? href : undefined;
          return (
            <a
              href={safeHref}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2 hover:opacity-80 transition-opacity"
            >
              {children}
            </a>
          );
        },

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

// Re-parsing markdown costs ~5ms per message (remark + rehype-highlight +
// KaTeX + sanitize). The chat thread re-renders on every streamed frame and
// on each run poll, so without this every historical message would be
// re-parsed each time. `content` is the only prop, so referential equality is
// exactly the right bail-out condition.
export const MarkdownRenderer = React.memo(MarkdownRendererBase);
