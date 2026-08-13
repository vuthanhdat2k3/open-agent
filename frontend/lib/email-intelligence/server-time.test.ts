import { describe, expect, it } from "vitest";
import { createServerClock, formatRemaining, remainingMs } from "./server-time";

describe("server time", () => {
  it("calculates countdown from server time and monotonic elapsed time", () => {
    const clock = createServerClock("2026-08-13T05:00:00.000Z", 1000);
    expect(remainingMs("2026-08-13T05:01:00.000Z", clock, 31000)).toBe(30000);
    expect(formatRemaining(0)).toBe("Đã hết hạn");
  });
});
