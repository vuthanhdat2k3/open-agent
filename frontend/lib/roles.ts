// Canonical role constants. Keep the union aligned with backend `app/models/role.py`
// (after the legacy `admin` alias was dropped) and the BE `/me` membership payload.
//
// `Role` is the type used everywhere on the FE; consumers that need a broader
// shape (legacy `admin` string still present in the wire for an in-flight
// migration) can fall back through `normalizeRole` below.
export type Role = "platform_admin" | "org_admin" | "operator" | "user";

export const ROLES: readonly Role[] = ["platform_admin", "org_admin", "operator", "user"] as const;

// Roles that an org admin can grant to a member through PATCH /api/orgs/{id}/members/{user_id}.
// `platform_admin` is intentionally absent — only a platform_admin can mint one,
// and the BE rejects any other input.
export const ASSIGNABLE_ROLES: readonly Role[] = ["org_admin", "operator", "user"] as const;

export function isPlatformAdmin(role: string | null | undefined): boolean {
  return role === "platform_admin";
}

export function isOrgAdmin(role: string | null | undefined): boolean {
  return role === "org_admin";
}

export function isOperator(role: string | null | undefined): boolean {
  return role === "operator";
}

export function isEndUser(role: string | null | undefined): boolean {
  return role === "user";
}

// Any role that owns organization configuration (org_admin or platform_admin).
// Used to gate admin-only UI without hardcoding role string comparisons.
export function isAdminRole(role: string | null | undefined): boolean {
  return role === "org_admin" || role === "platform_admin";
}

// Any role with operational/management visibility (operator, org_admin, or platform_admin).
export function isOperatorOrAdmin(role: string | null | undefined): boolean {
  return role === "operator" || role === "org_admin" || role === "platform_admin";
}

// Coerce a role value coming from the wire (BE or local storage) to the canonical
// `Role` type. The legacy `admin` spelling is normalized to `org_admin` so FE code
// only ever sees canonical values.
export function normalizeRole(value: string | null | undefined): Role {
  if (value === "platform_admin" || value === "org_admin" || value === "operator" || value === "user") {
    return value;
  }
  if (value === "admin") return "org_admin";
  return "user";
}
