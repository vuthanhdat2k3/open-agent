export function emailIntelligenceQueryKeys(orgId: string | null) {
  const scope = orgId || "anonymous";
  return {
    navigation: ["email-intelligence", scope, "navigation-summary"] as const,
    emails: (filters: unknown = {}) => ["email-intelligence", scope, "emails", filters] as const,
    email: (id: string | null) => ["email-intelligence", scope, "email", id] as const,
    notifications: (filters: unknown = {}) => ["email-intelligence", scope, "notifications", filters] as const,
    cases: (filters: unknown = {}) => ["customer-intelligence", scope, "cases", filters] as const,
    case: (id: string | null) => ["customer-intelligence", scope, "case", id] as const,
    approvals: (filters: unknown = {}) => ["email-intelligence", scope, "approvals", filters] as const,
    rules: (filters: unknown = {}) => ["email-intelligence", scope, "rules", filters] as const,
    connections: ["email-intelligence", scope, "connections"] as const,
    adminOverview: ["admin-email-intelligence", scope, "overview"] as const,
  };
}
