import { describe, expect, it } from "vitest";
import { inlineCodeHttpUrl, normalizeLatex } from "../lib/chat/markdown-text";

describe("normalizeLatex", () => {
  it("keeps standard markdown links with http(s) destinations intact", () => {
    const md = "[Open preview](https://example.com/preview)";
    expect(normalizeLatex(md)).toBe(md);
  });

  it("keeps bare URLs wrapped in plain parentheses intact", () => {
    const md = "See (https://example.com/a=b?c=d) for details";
    expect(normalizeLatex(md)).toBe(md);
  });

  it("keeps relative markdown link destinations intact", () => {
    const md = "[Docs](/guide/getting-started)";
    expect(normalizeLatex(md)).toBe(md);
  });

  it("still converts LaTeX inline delimiters", () => {
    expect(normalizeLatex("\\(x + y\\)")).toBe("$x + y$");
  });

  it("still converts LaTeX display delimiters", () => {
    expect(normalizeLatex("\\[E = mc^2\\]")).toBe("\n$$\nE = mc^2\n$$\n");
  });

  it("keeps regular text in parentheses intact without turning into math", () => {
    expect(normalizeLatex("(a + b)")).toBe("(a + b)");
    expect(normalizeLatex("range (1 - 10) or (from A to B)")).toBe("range (1 - 10) or (from A to B)");
    expect(normalizeLatex("Ví dụ (1 + 2 = 3)")).toBe("Ví dụ (1 + 2 = 3)");
  });
});

describe("inlineCodeHttpUrl", () => {
  it("accepts an exact absolute http URL", () => {
    expect(inlineCodeHttpUrl("http://localhost:3000/preview")).toBe("http://localhost:3000/preview");
  });

  it("accepts an exact absolute https URL with query and port", () => {
    expect(inlineCodeHttpUrl("https://example.com/x?token=abc#f")).toBe(
      "https://example.com/x?token=abc#f",
    );
  });

  it("rejects values with surrounding whitespace", () => {
    expect(inlineCodeHttpUrl(" http://example.com ")).toBeUndefined();
  });

  it("rejects commands and partial URLs", () => {
    expect(inlineCodeHttpUrl("curl http://example.com")).toBeUndefined();
    expect(inlineCodeHttpUrl("example.com/path")).toBeUndefined();
  });

  it("rejects dangerous protocols", () => {
    expect(inlineCodeHttpUrl("javascript:alert(1)")).toBeUndefined();
    expect(inlineCodeHttpUrl("file:///etc/passwd")).toBeUndefined();
  });
});
