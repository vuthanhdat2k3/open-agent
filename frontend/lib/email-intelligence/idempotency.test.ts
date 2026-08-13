import { describe, expect, it } from "vitest";
import { createIdempotencyKey } from "./idempotency";

describe("idempotency", () => {
  it("creates a non-empty unique client key", () => {
    const first = createIdempotencyKey();
    const second = createIdempotencyKey();
    expect(first).not.toBe(second);
    expect(first.length).toBeGreaterThan(10);
  });
});
