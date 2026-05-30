import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockDiffSummary } from "../mock/studioMock";
import { DiffSummary } from "./DiffSummary";

describe("DiffSummary", () => {
  it("renders helpful, harmful, and skipped diff sections", () => {
    render(<DiffSummary diff={mockDiffSummary} />);

    expect(screen.getByText("Helpful Deltas")).toBeInTheDocument();
    expect(screen.getByText("Harmful Deltas")).toBeInTheDocument();
    expect(screen.getByText("Skipped Parts")).toBeInTheDocument();
    expect(screen.getByText("hat_asymmetry +0.7")).toBeInTheDocument();
    expect(screen.getByText("side_projection_iou -0.003")).toBeInTheDocument();
    expect(screen.getByText("equipment/shield/sword: part_not_present")).toBeInTheDocument();
  });
});
