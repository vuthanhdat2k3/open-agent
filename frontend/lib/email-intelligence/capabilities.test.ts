import { describe, expect, it } from "vitest";
import { blockedReason, can, hasExecutableCapabilities } from "./capabilities";

describe("capabilities", () => {
  it("fails closed when capability is absent", () => {
    expect(can(undefined, "can_approve")).toBe(false);
    expect(hasExecutableCapabilities(undefined)).toBe(false);
  });

  it("exposes server blocked reason without inferring authorization", () => {
    const capabilities = { can_approve: false, blocked_reasons: { approve: "approval.expired" } };
    expect(can(capabilities, "can_approve")).toBe(false);
    expect(blockedReason(capabilities, "approve")).toBe("approval.expired");
  });
});
