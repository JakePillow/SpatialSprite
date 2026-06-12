import { afterEach, describe, expect, it, vi } from "vitest";
import { createAssetFromCandidates, deleteAsset, renameAsset } from "./assets";
import { listRawSheets, uploadRawSheet } from "./sheets";
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

  it("reads raw sheet listings", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ok: true,
            sheets: [{ sheet_id: "sheet.png", filename: "sheet.png", path: "assets/raw/sheet.png", width: 32, height: 32 }]
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        )
      )
    );

    await expect(listRawSheets()).resolves.toMatchObject({ sheets: [{ filename: "sheet.png" }] });
  });

  it("uploads a raw sheet as a file body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          sheet: { sheet_id: "sheet.png", filename: "sheet.png", path: "assets/raw/sheet.png", width: 32, height: 32 }
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["sheet"], "sheet.png", { type: "image/png" });

    await expect(uploadRawSheet(file)).resolves.toMatchObject({ sheet: { filename: "sheet.png" } });

    expect(fetchMock.mock.calls[0][0]).toContain("/raw-sheets/upload?filename=sheet.png");
    expect(fetchMock.mock.calls[0][1].body).toBe(file);
  });

  it("sends candidate_id assignments when creating an asset", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: true,
          asset_id: "mario_clean_test",
          asset_dir: "assets/samples/mario_clean_test",
          spriteasset_path: "assets/samples/mario_clean_test/spriteasset_v1.json",
          created_files: []
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" }
        }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await createAssetFromCandidates({
      asset_id: "mario_clean_test",
      candidate_run_dir: "outputs/mario/view_candidates/run_001",
      selection_version: "view_selection_v1",
      mode: "strict",
      selection: { front: 20, side: 30, back: 10 },
      source_coverage: { front: "authored", back: "authored" }
    });

    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request.selection_version).toBe("view_selection_v1");
    expect(request.selection).toEqual({ front: 20, side: 30, back: 10 });
  });

  it("renames an asset", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, asset: { asset_id: "new_asset", path: "assets/samples/new_asset/spriteasset_v1.json" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await renameAsset("old_asset", "new_asset");

    expect(fetchMock.mock.calls[0][0]).toContain("/assets/old_asset");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ new_asset_id: "new_asset" });
  });

  it("deletes an asset", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, asset_id: "old_asset" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await deleteAsset("old_asset");

    expect(fetchMock.mock.calls[0][0]).toContain("/assets/old_asset");
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
  });
});
