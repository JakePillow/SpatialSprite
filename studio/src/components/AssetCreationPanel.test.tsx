import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CandidateRun } from "../types/studio";
import { AssetCreationPanel } from "./AssetCreationPanel";

const candidateRun: CandidateRun = {
  run_id: "run_001",
  out_dir: "outputs/mario/view_candidates/run_001",
  candidate_contact_sheet: "outputs/mario/view_candidates/run_001/candidate_contact_sheet.png",
  candidates: [{ candidate_id: 0, path: "/placeholders/front.svg" }]
};

describe("AssetCreationPanel", () => {
  it("disables creation for an invalid asset id", () => {
    render(
      <AssetCreationPanel
        assetId="Bad Asset"
        candidateRun={candidateRun}
        assignments={{ front: 0 }}
        selectionMode="strict"
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onCreate={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /create only/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /create & build/i })).toBeDisabled();
    expect(screen.getByText(/lowercase letters/i)).toBeInTheDocument();
  });

  it("disables creation when front is missing", () => {
    render(
      <AssetCreationPanel
        assetId="valid_asset"
        candidateRun={candidateRun}
        assignments={{ back: 1 }}
        selectionMode="strict"
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onCreate={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /create only/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /create & build/i })).toBeDisabled();
    expect(screen.getByText(/Front view is required/i)).toBeInTheDocument();
  });

  it("keeps strict creation disabled until side and back are assigned", () => {
    render(
      <AssetCreationPanel
        assetId="valid_asset"
        candidateRun={candidateRun}
        assignments={{ front: 0 }}
        selectionMode="strict"
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onCreate={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /create only/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /create & build/i })).toBeDisabled();
    expect(screen.getByText(/Side view is required in strict mode/i)).toBeInTheDocument();
    expect(screen.getByText(/Back view is required in strict mode/i)).toBeInTheDocument();
  });

  it("enables prototype creation for a valid front assignment and warns about missing side/back", () => {
    const onCreate = vi.fn();
    render(
      <AssetCreationPanel
        assetId="valid_asset"
        candidateRun={candidateRun}
        assignments={{ front: 0 }}
        selectionMode="prototype"
        warnings={["Back will be inferred. Fidelity will be limited."]}
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onCreate={onCreate}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /create only/i }));

    expect(onCreate).toHaveBeenCalled();
    expect(screen.getByText(/Back will be inferred/i)).toBeInTheDocument();
  });

  it("runs the combined create and build action", () => {
    const onCreateAndBuild = vi.fn();
    render(
      <AssetCreationPanel
        assetId="valid_asset"
        candidateRun={candidateRun}
        assignments={{ front: 0, side: 1, back: 2 }}
        selectionMode="strict"
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={vi.fn()}
        onSelectionModeChange={vi.fn()}
        onCreate={vi.fn()}
        onCreateAndBuild={onCreateAndBuild}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /create & build/i }));

    expect(onCreateAndBuild).toHaveBeenCalled();
  });

  it("offers a new asset id action", () => {
    const onGenerateAssetId = vi.fn();
    render(
      <AssetCreationPanel
        assetId="my_character"
        candidateRun={candidateRun}
        assignments={{ front: 0, side: 1, back: 2 }}
        selectionMode="strict"
        onAssetIdChange={vi.fn()}
        onGenerateAssetId={onGenerateAssetId}
        onSelectionModeChange={vi.fn()}
        onCreate={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /new id/i }));

    expect(onGenerateAssetId).toHaveBeenCalled();
  });
});
