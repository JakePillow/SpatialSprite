import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockAssets } from "../mock/studioMock";
import { AssetBrowser } from "./AssetBrowser";

describe("AssetBrowser", () => {
  it("selects an asset from the mock asset list", () => {
    const onSelectAsset = vi.fn();
    render(<AssetBrowser assets={mockAssets} selectedAssetId="hero" onSelectAsset={onSelectAsset} />);

    fireEvent.click(screen.getByRole("button", { name: /hero_side_fixture/i }));

    expect(onSelectAsset).toHaveBeenCalledWith("hero_side_fixture");
  });
});
