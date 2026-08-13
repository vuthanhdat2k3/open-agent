export type Capabilities = Record<string, boolean | Record<string, string>> & {
  blocked_reasons?: Record<string, string>;
};

export function can(capabilities: Capabilities | null | undefined, action: string): boolean {
  return capabilities?.[action] === true;
}

export function blockedReason(capabilities: Capabilities | null | undefined, action: string): string | null {
  return capabilities?.blocked_reasons?.[action] || null;
}

export function hasExecutableCapabilities(capabilities: Capabilities | null | undefined): boolean {
  if (!capabilities) return false;
  return Object.entries(capabilities).some(([key, value]) => key.startsWith("can_") && value === true);
}
