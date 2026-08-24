import { afterEach, describe, expect, it } from "vitest";
import { randomId } from "./utils";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("randomId", () => {
  const originalCrypto = globalThis.crypto;

  afterEach(() => {
    Object.defineProperty(globalThis, "crypto", {
      value: originalCrypto,
      writable: true,
      configurable: true,
    });
  });

  it("uses crypto.randomUUID when available (secure context)", () => {
    Object.defineProperty(globalThis, "crypto", {
      value: { randomUUID: () => "secure-context-id", getRandomValues: originalCrypto.getRandomValues },
      writable: true,
      configurable: true,
    });
    expect(randomId()).toBe("secure-context-id");
  });

  it("falls back to a valid v4 UUID in insecure contexts where randomUUID is undefined", () => {
    // Reproduces http://127.0.0.1.sslip.io:3000 — isSecureContext === false,
    // crypto.randomUUID does not exist. Chat send() must not crash here.
    Object.defineProperty(globalThis, "crypto", {
      value: {
        getRandomValues: (...args: Parameters<Crypto["getRandomValues"]>) =>
          originalCrypto.getRandomValues(...args),
      },
      writable: true,
      configurable: true,
    });
    const id = randomId();
    expect(id).toMatch(UUID_RE);
  });
});
