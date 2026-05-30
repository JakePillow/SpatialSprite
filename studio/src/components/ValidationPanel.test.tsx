import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockValidation } from "../mock/studioMock";
import { ValidationPanel } from "./ValidationPanel";

describe("ValidationPanel", () => {
  it("renders validation status and key metrics", () => {
    render(<ValidationPanel validation={mockValidation} />);

    expect(screen.getAllByText("PASS").length).toBeGreaterThan(0);
    expect(screen.getByText("mesh_connected_components")).toBeInTheDocument();
    expect(screen.getByText("degenerate_faces")).toBeInTheDocument();
    expect(screen.getByText("non_manifold_edges")).toBeInTheDocument();
    expect(screen.getByText("validation_passed")).toBeInTheDocument();
  });
});
