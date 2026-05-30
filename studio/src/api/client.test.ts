import { afterEach, describe, expect, it, vi } from "vitest";
import { health } from "./studioApi";

describe("Studio API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads /health successfully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: true, service: "spritespatial-studio-api", version: "0.1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      )
    );

    await expect(health()).resolves.toMatchObject({ ok: true, service: "spritespatial-studio-api" });
  });

  it("reports fetch failures with a useful error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(health()).rejects.toThrow(/offline/);
  });
});
