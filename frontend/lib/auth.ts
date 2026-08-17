"use client";

let accessToken: string | null = null;
let sessionAuthenticated = false;
let refreshPromise: Promise<string | null> | null = null;
const listeners = new Set<(token: string | null) => void>();

export function getAccessToken() {
  return accessToken;
}

export function getActiveOrgId(): string | null {
  if (!accessToken) return null;
  try {
    const parts = accessToken.split(".");
    if (parts.length < 2) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload.org_id || null;
  } catch {
    return null;
  }
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  sessionAuthenticated = Boolean(token);
  listeners.forEach((listener) => listener(accessToken));
}

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const name = "openagent_csrf=";
  const value = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(name));
  return value ? decodeURIComponent(value.slice(name.length)) : null;
}

export function isAuthenticated() {
  return sessionAuthenticated || Boolean(accessToken);
}

export function markSessionAuthenticated(authenticated: boolean) {
  sessionAuthenticated = authenticated;
  if (!authenticated) accessToken = null;
  listeners.forEach((listener) => listener(accessToken));
}

export function subscribeAuth(listener: (token: string | null) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function refreshAccessToken() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const session = await fetch("/api/auth/me", { credentials: "include" });
    if (session.ok) {
      markSessionAuthenticated(true);
      return "__application_session__";
    }
    const res = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
    if (!res.ok) {
      setAccessToken(null);
      return null;
    }
    const data = (await res.json()) as { access_token: string };
    setAccessToken(data.access_token);
    return data.access_token;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}
