import type { CanvasItem } from "@/stores";

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

export interface AutoOpenContext {
  openCanvas: (item: CanvasItem) => void;
  lastOpenedKeyRef?: { current: string | null };
}

export function isWebPreviewable(pathOrExt: string): boolean {
  const p = pathOrExt.toLowerCase();
  return p.endsWith(".html") || p.endsWith(".htm") || p.endsWith(".svg");
}

export function tryAutoOpenCanvasFromTool(
  toolName: string,
  argsRaw?: any,
  resultRaw?: any,
  ctx?: AutoOpenContext,
): boolean {
  if (!ctx?.openCanvas) return false;
  const { openCanvas, lastOpenedKeyRef } = ctx;

  let args: any = null;
  let result: any = null;

  if (argsRaw != null) {
    if (typeof argsRaw === "object") args = argsRaw;
    else if (typeof argsRaw === "string") {
      try {
        args = JSON.parse(argsRaw);
      } catch {}
    }
  }

  if (resultRaw != null) {
    if (typeof resultRaw === "object") result = resultRaw;
    else if (typeof resultRaw === "string") {
      try {
        result = JSON.parse(resultRaw);
      } catch {}
    }
  }

  // 1. Workflow Tools (workflow_create, workflow_run, workflow_get, workflow_update, workflow_get_run)
  if (toolName.startsWith("workflow_")) {
    const wfId = result?.id || result?.workflow_id || args?.workflow_id || args?.id;
    const runId = result?.run_id || args?.run_id;
    const name = result?.name || result?.workflow_name || args?.name || "Workflow DAG";
    const desc = result?.description || args?.description;
    const graph = result?.graph || args?.graph;

    // Do not auto-open if neither id nor graph nor runId is known yet
    if (!wfId && !runId && !graph && !args?.name) {
      return false;
    }

    const actionKey = `workflow:${wfId || name}:${runId || ""}:${toolName}`;
    if (lastOpenedKeyRef && lastOpenedKeyRef.current === actionKey) {
      return false;
    }
    if (lastOpenedKeyRef) {
      lastOpenedKeyRef.current = actionKey;
    }

    openCanvas({
      type: "workflow",
      title: name,
      workflowId: wfId,
      workflowName: name,
      workflowDescription: desc,
      workflowRunId: runId,
      workflowGraph: graph,
      code: graph
        ? JSON.stringify(graph, null, 2)
        : typeof resultRaw === "string"
        ? resultRaw
        : typeof argsRaw === "string"
        ? argsRaw
        : undefined,
      language: "json",
      initialTab: "workflow",
    });
    return true;
  }

  // 2. File Writing Tool
  if (toolName === "write_file") {
    const path = args?.path || args?.filename || result?.path;
    const content = args?.content || args?.code || result?.content;
    if (!path && !content) return false;

    const filename = path ? path.split(/[/\\]/).pop() || path : "file";
    const actionKey = `file:${path || filename}:${(content || "").length}`;
    if (lastOpenedKeyRef && lastOpenedKeyRef.current === actionKey) {
      return false;
    }
    if (lastOpenedKeyRef) {
      lastOpenedKeyRef.current = actionKey;
    }

    openCanvas({
      type: "file",
      title: filename,
      code: content || "",
      filePath: path,
      language: inferLanguage(filename),
      initialTab: isWebPreviewable(filename) ? "preview" : "code",
    });
    return true;
  }

  // 3. Code Execution Tool
  if (toolName === "run_code") {
    const code = args?.code || result?.code;
    const lang = args?.language || result?.language || "python";
    const path = args?.path || result?.path;
    if (!code) return false;

    const filename = path ? path.split(/[/\\]/).pop()! : `${lang} script`;
    const actionKey = `code:${filename}:${code.slice(0, 40)}`;
    if (lastOpenedKeyRef && lastOpenedKeyRef.current === actionKey) {
      return false;
    }
    if (lastOpenedKeyRef) {
      lastOpenedKeyRef.current = actionKey;
    }

    openCanvas({
      type: "code",
      title: filename,
      code,
      language: lang,
      initialTab: "code",
    });
    return true;
  }

  // 4. Web Artifact Preview Tool
  if (toolName === "preview_web_artifact") {
    const path = args?.path || result?.path || "preview.html";
    const content = args?.content || args?.html || result?.content || "";
    const filename = path.split(/[/\\]/).pop() || path;
    const actionKey = `web:${filename}:${content.slice(0, 40)}`;
    if (lastOpenedKeyRef && lastOpenedKeyRef.current === actionKey) {
      return false;
    }
    if (lastOpenedKeyRef) {
      lastOpenedKeyRef.current = actionKey;
    }

    openCanvas({
      type: "file",
      title: filename,
      code: content,
      language: "html",
      initialTab: "preview",
    });
    return true;
  }

  return false;
}

export function tryAutoOpenCanvasFromArtifact(
  artifact: { name?: string; filename?: string; content_url?: string; download_url?: string; id?: string },
  ctx?: AutoOpenContext,
): boolean {
  if (!ctx?.openCanvas || (!artifact?.name && !artifact?.filename)) return false;
  const { openCanvas, lastOpenedKeyRef } = ctx;

  const title = artifact.name || artifact.filename || "file";
  const actionKey = `artifact:${artifact.id || title}`;
  if (lastOpenedKeyRef && lastOpenedKeyRef.current === actionKey) {
    return false;
  }
  if (lastOpenedKeyRef) {
    lastOpenedKeyRef.current = actionKey;
  }

  const contentUrl = artifact.content_url || (artifact.id ? `/api/files/${artifact.id}/content` : undefined);
  const downloadUrl = artifact.download_url || contentUrl;

  openCanvas({
    type: "file",
    title,
    contentUrl,
    downloadUrl,
    language: inferLanguage(title),
    initialTab: isWebPreviewable(title) ? "preview" : "code",
  });
  return true;
}

