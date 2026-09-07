"use client";

/**
 * UI Action Registry — the only way a `ui_action` SSE event (see
 * backend/app/core/tools/ui_actions.py) is allowed to touch the DOM.
 *
 * Deliberately NOT a generic `runJs`/`click(selector)` escape hatch: the
 * agent can only invoke capabilities a page has explicitly registered via
 * `usePageContext()` (added in P2). This is the guardrail from
 * docs/companion-operator-agent-v2-spec.md §7 — content an LLM generates
 * must never be used as a selector or URL executed blindly.
 */

import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";

export interface UiActionResult {
  ok: boolean;
  result?: Record<string, unknown>;
  error?: string;
}

export interface PageCapabilities {
  route: string;
  title?: string;
  /** Current filter state, echoed back by ui_read_screen. */
  filters?: Record<string, unknown>;
  selection?: { type: string; id: string; label?: string } | null;
  visible?: Array<{ type: string; id: string; label: string; status?: string }>;
  /** Applies a filter patch; returns the filters actually in effect. */
  setFilter?: (filters: Record<string, unknown>) => Promise<Record<string, unknown>> | Record<string, unknown>;
  /** Registered panel name -> opener. */
  panels?: Record<string, (id?: string) => Promise<void> | void>;
  /** Registered form name -> {fill, submit}. submit is optional (read-only forms never allow it). */
  forms?: Record<
    string,
    {
      fill: (values: Record<string, unknown>) => Promise<void> | void;
      submit?: (values: Record<string, unknown>) => Promise<Record<string, unknown>> | Record<string, unknown>;
    }
  >;
}

let currentCapabilities: PageCapabilities | null = null;

/** Called by usePageContext() on every route/state change (P2). */
export function setPageCapabilities(caps: PageCapabilities | null): void {
  currentCapabilities = caps;
}

export function getPageCapabilities(): PageCapabilities | null {
  return currentCapabilities;
}

// Routes the App Operator is allowed to navigate to. Kept as an explicit
// allowlist (not "any string the model produces") per the spec's guardrail
// principle — an unregistered route is rejected rather than silently
// attempted.
const NAVIGABLE_ROUTES = [
  "/",
  "/chat",
  "/workflows",
  "/reports",
  "/integrations",
  "/channels",
  "/email-intelligence",
  "/customer-intelligence",
  "/files",
  "/workspace",
  "/approvals",
  "/organizations",
  "/admin/platform-config",
] as const;

function buildUrl(route: string, params?: Record<string, unknown>): string | null {
  if (!NAVIGABLE_ROUTES.includes(route as (typeof NAVIGABLE_ROUTES)[number])) return null;
  if (!params || Object.keys(params).length === 0) return route;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const query = qs.toString();
  return query ? `${route}?${query}` : route;
}

export async function executeUiAction(
  tool: string,
  args: Record<string, unknown>,
  router: AppRouterInstance,
): Promise<UiActionResult> {
  try {
    switch (tool) {
      case "ui_read_screen": {
        const caps = currentCapabilities;
        return {
          ok: true,
          result: {
            route: caps?.route ?? window.location.pathname,
            title: caps?.title ?? document.title,
            filters: caps?.filters ?? {},
            selection: caps?.selection ?? null,
            visible: caps?.visible ?? [],
            capabilities: [
              ...(caps?.setFilter ? ["ui_set_filter"] : []),
              ...Object.keys(caps?.panels ?? {}).map((p) => `ui_open_panel:${p}`),
              ...Object.keys(caps?.forms ?? {}).map((f) => `ui_fill_form:${f}`),
            ],
          },
        };
      }

      case "ui_navigate": {
        const route = String(args.route ?? "");
        const url = buildUrl(route, args.params as Record<string, unknown> | undefined);
        if (!url) return { ok: false, error: `route '${route}' is not navigable` };
        router.push(url);
        await new Promise((r) => setTimeout(r, 300)); // let the route settle before the agent reads the screen again
        return { ok: true, result: { route } };
      }

      case "ui_set_filter": {
        const caps = currentCapabilities;
        if (!caps?.setFilter) return { ok: false, error: "the current page has no filters registered" };
        const filters = args.filters as Record<string, unknown>;
        const applied = await caps.setFilter(filters);
        return { ok: true, result: { filters: applied } };
      }

      case "ui_open_panel": {
        const caps = currentCapabilities;
        const panel = String(args.panel ?? "");
        const opener = caps?.panels?.[panel];
        if (!opener) return { ok: false, error: `panel '${panel}' is not registered on the current page` };
        await opener(args.id as string | undefined);
        return { ok: true, result: { panel } };
      }

      case "ui_fill_form": {
        const caps = currentCapabilities;
        const form = String(args.form ?? "");
        const entry = caps?.forms?.[form];
        if (!entry) return { ok: false, error: `form '${form}' is not registered on the current page` };
        await entry.fill(args.values as Record<string, unknown>);
        return { ok: true, result: { form, filled: true } };
      }

      case "ui_submit_form": {
        const caps = currentCapabilities;
        const form = String(args.form ?? "");
        const entry = caps?.forms?.[form];
        if (!entry?.submit) return { ok: false, error: `form '${form}' does not accept submission` };
        const values = (args.values as Record<string, unknown>) ?? {};
        await entry.fill(values);
        const result = await entry.submit(values);
        return { ok: true, result: { form, ...result } };
      }

      default:
        return { ok: false, error: `unknown ui action '${tool}'` };
    }
  } catch (err: any) {
    return { ok: false, error: err?.message || String(err) };
  }
}
