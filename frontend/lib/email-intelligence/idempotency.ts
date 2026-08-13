export function createIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export type CommandState = "idle" | "submitting" | "succeeded" | "conflicted" | "verifying_outcome" | "failed";
