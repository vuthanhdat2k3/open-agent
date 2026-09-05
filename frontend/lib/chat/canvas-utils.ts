export function inferLanguage(filename: string): string {
  if (!filename.includes(".")) {
    return "plaintext";
  }
  const ext = (filename.split(".").pop() || "").toLowerCase();
  switch (ext) {
    case "py":
      return "python";
    case "js":
    case "mjs":
    case "cjs":
      return "javascript";
    case "ts":
    case "tsx":
      return "typescript";
    case "jsx":
      return "javascript";
    case "html":
    case "htm":
    case "svg":
      return "html";
    case "sh":
    case "bash":
      return "bash";
    case "json":
      return "json";
    case "sql":
      return "sql";
    case "css":
      return "css";
    case "md":
    case "markdown":
      return "markdown";
    case "yaml":
    case "yml":
      return "yaml";
    default:
      return ext || "plaintext";
  }
}
