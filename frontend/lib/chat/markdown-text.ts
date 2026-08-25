/**
 * Pure text transforms shared by the chat markdown renderer and its tests.
 * Kept free of JSX so vitest can import them without a React transform.
 */

/**
 * Converts the various LaTeX delimiter styles that LLMs commonly produce
 * into the `$…$` / `$$…$$` style that remark-math recognises.
 */
export function normalizeLatex(text: string): string {
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
  //    - The parenthesis does not close a markdown link destination `](…)`
  //    - It is not preceded by \left or followed by \right (lookbehinds)
  //    - It contains no URL (://) — link destinations would be mangled into math
  //    - It contains a backslash, operator, or is a single variable/function call to prevent text matching
  text = text.replace(/(?<!\\left)(?<!\])\(\s*([\s\S]*?)\s*(?<!\\right)\)/g, (match, inner) => {
    const trimmed = inner.trim();
    if (trimmed.length === 0 || trimmed.length > 150) return match;
    if (/https?:\/\//.test(trimmed)) return match;

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

  // 6. Restore the protected math blocks in reverse order. The replacement
  //    must be a function: a string replacement would interpret `$$` as an
  //    escaped literal `$` and halve every display-math delimiter.
  for (let i = placeholders.length - 1; i >= 0; i--) {
    text = text.replace(`___LATEX_PLACEHOLDER_${i}___`, () => placeholders[i]);
  }

  return text;
}

/**
 * The complete inline-code value when it is exactly an absolute HTTP(S) URL
 * (no surrounding whitespace) — deepseek-harness parity: such tokens keep
 * their code chrome but become safe external links. Anything else stays
 * inert code.
 */
export function inlineCodeHttpUrl(value: string): string | undefined {
  if (value.trim() !== value) return undefined;
  try {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:" ? value : undefined;
  } catch {
    return undefined;
  }
}
