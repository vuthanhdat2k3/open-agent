// API client — calls are relative (/api/...) because next.config.mjs proxies
// /api/* to the FastAPI backend on :8000.
import { getAccessToken, getActiveOrgId, getCsrfToken, refreshAccessToken } from "@/lib/auth";
import { apiBaseUrl } from "@/lib/utils";

export interface SseEvent {
  event: string;
  data: any;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly correlationId: string | null;
  readonly retryable: boolean;

  constructor(status: number, message: string, options: { code?: string | null; correlationId?: string | null; retryable?: boolean } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code ?? null;
    this.correlationId = options.correlationId ?? null;
    this.retryable = options.retryable ?? status >= 500;
  }
}

export type ApiRequestOptions = { headers?: HeadersInit };

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const token = getAccessToken();
  const csrf = getCsrfToken();
  const orgId = getActiveOrgId();
  const res = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(csrf && init?.method && !["GET", "HEAD", "OPTIONS"].includes(init.method) ? { "X-CSRF-Token": csrf } : {}),
      ...(orgId ? { "X-Org-Id": orgId } : {}),
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401 && !retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return request<T>(path, init, true);
    }
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) {
    let detail = res.statusText;
    let errorMeta: { code?: string | null; correlationId?: string | null; retryable?: boolean } = {};
    try {
      const j = await res.json();
      detail = (j && (j.error?.message || j.detail)) || detail;
      if (j?.error) {
        errorMeta = {
          code: j.error.code,
          correlationId: j.error.correlation_id,
          retryable: j.error.retryable,
        };
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail, errorMeta);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined, headers: options?.headers }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined, headers: options?.headers }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// Streaming SSE consumer for chat + workflow runs.
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
  retried = false,
): Promise<void> {
  // Call the backend directly (not through next.config.mjs rewrites): Next's
  // rewrite proxy does not reliably forward incremental SSE chunks — it can
  // hold the connection open for the full duration and then deliver only the
  // first and last chunk, dropping everything streamed in between.
  const res = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
      ...(getCsrfToken() ? { "X-CSRF-Token": getCsrfToken()! } : {}),
      ...(getActiveOrgId() ? { "X-Org-Id": getActiveOrgId()! } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401 && !retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return streamSSE(path, body, onEvent, signal, true);
  }
  if (!res.ok || !res.body) {
    throw new Error(`stream failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal?.aborted) {
      await reader.cancel().catch(() => {});
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let event = "message";
      let dataStr = "";
      for (const line of lines) {
        // SSE comment lines (heartbeat `: ping`) carry no event/data and are ignored.
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (dataStr) {
        try {
          onEvent({ event, data: JSON.parse(dataStr) });
        } catch {
          // ignore malformed
        }
      }
    }
  }
}

// GET variant of streamSSE: the chat event-log endpoint is a GET with query
// params (replay + follow), so it cannot reuse the JSON-POST reader above.
export async function streamSSEGet(
  url: string,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal,
  retried = false,
): Promise<void> {
  const res = await fetch(`${apiBaseUrl}${url}`, {
    credentials: "include",
    headers: {
      ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
      ...(getCsrfToken() ? { "X-CSRF-Token": getCsrfToken()! } : {}),
      ...(getActiveOrgId() ? { "X-Org-Id": getActiveOrgId()! } : {}),
    },
    signal,
  });
  if (res.status === 401 && !retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return streamSSEGet(url, onEvent, signal, true);
  }
  if (!res.ok || !res.body) {
    throw new Error(`stream failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal?.aborted) {
      await reader.cancel().catch(() => {});
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let event = "message";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      if (dataStr) {
        try {
          onEvent({ event, data: JSON.parse(dataStr) });
        } catch {
          // ignore malformed
        }
      }
    }
  }
}
