import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes));
}

// crypto.randomUUID only exists in secure contexts (HTTPS or localhost).
// This app is routinely served over plain HTTP on non-localhost hosts such as
// http://127.0.0.1.sslip.io:3000 (required by the ZITADEL deployment), where
// calling it throws and silently kills chat sends. Fall back to a v4 UUID
// built from getRandomValues, which IS available in insecure contexts.
export function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
