import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockAssets } from "../mock/studioMock";
import { AssetBrowser } from "./AssetBrowser";

describe("AssetBrowser", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("selects an asset from the mock asset list", () => {
    const onSelectAsset = vi.fn();
    render(<AssetBrowser {...baseProps()} selectedAssetId="hero" onSelectAsset={onSelectAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /select asset hero_side_fixture/i }));

    expect(onSelectAsset).toHaveBeenCalledWith("hero_side_fixture");
  });

  it("starts a new asset workflow", () => {
    const onNewAsset = vi.fn();
    render(<AssetBrowser {...baseProps()} selectedAssetId="hero" onNewAsset={onNewAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /new asset/i }));

    expect(onNewAsset).toHaveBeenCalled();
  });

  it("renames an asset inline", () => {
    const onRenameAsset = vi.fn();
    render(<AssetBrowser {...baseProps()} selectedAssetId="hero" onRenameAsset={onRenameAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /rename hero_side_fixture/i }));
    fireEvent.change(screen.getByRole("textbox", { name: /rename hero_side_fixture/i }), {
      target: { value: "renamed_asset" }
    });
    fireEvent.click(screen.getByRole("button", { name: /save hero_side_fixture rename/i }));

    expect(onRenameAsset).toHaveBeenCalledWith("hero_side_fixture", "renamed_asset");
  });

  it("deletes an asset after confirmation", () => {
    const onDeleteAsset = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AssetBrowser {...baseProps()} selectedAssetId="hero" onDeleteAsset={onDeleteAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /delete hero_side_fixture/i }));

    expect(onDeleteAsset).toHaveBeenCalledWith("hero_side_fixture");
  });

  it("reorders assets", () => {
    const onMoveAsset = vi.fn();
    render(<AssetBrowser {...baseProps()} selectedAssetId="hero" onMoveAsset={onMoveAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /move hero_side_fixture up/i }));

    expect(onMoveAsset).toHaveBeenCalledWith("hero_side_fixture", "up");
  });
});

function baseProps() {
  return {
    assets: mockAssets,
    selectedAssetId: "hero",
    onSelectAsset: vi.fn(),
    onNewAsset: vi.fn(),
    onRenameAsset: vi.fn(),
    onDeleteAsset: vi.fn(),
    onMoveAsset: vi.fn()
  };
}
