import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/MeshViewer", () => ({
  MeshViewer: () => <div>Mesh Viewer Mock</div>
}));

import { Studio } from "./Studio";

describe("Studio workflow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to MOCK mode when the backend is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    render(<Studio />);

    await waitFor(() => expect(screen.getByText("MOCK")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/Studio API unavailable/i)).toBeInTheDocument());
  });

  it("applies a mock preset and updates validation state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Studio />);

    fireEvent.click(screen.getByRole("button", { name: /apply preset/i }));

    await waitFor(() => expect(screen.getByText(/pull_hat_back@0.75/)).toBeInTheDocument());
    expect(screen.getByText("validation_passed")).toBeInTheDocument();
  });

  it("creates and builds from candidate review", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Studio />);

    fireEvent.click(screen.getByRole("button", { name: /extract candidates/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /id 0/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /id 0/i }));
    fireEvent.click(screen.getByRole("button", { name: /id 2/i }));
    fireEvent.click(screen.getByRole("button", { name: /id 1/i }));
    fireEvent.click(screen.getByRole("button", { name: /create & build/i }));

    await waitFor(() => expect(screen.getAllByText(/build_mock_/).length).toBeGreaterThan(0));
    expect(screen.getByText("mesh_connected_components")).toBeInTheDocument();
    expect(screen.getByText("semantic_label_preservation_passed")).toBeInTheDocument();
  });

  it("extracts mock candidates and assigns a front view when offline", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Studio />);

    fireEvent.click(screen.getByRole("button", { name: /extract candidates/i }));

    await waitFor(() => expect(screen.getByRole("button", { name: /id 0/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /id 0/i }));
    fireEvent.click(screen.getByRole("button", { name: /id 2/i }));
    fireEvent.click(screen.getByRole("button", { name: /id 1/i }));
    fireEvent.click(screen.getByRole("button", { name: /create only/i }));

    expect(screen.getByAltText(/front candidate 0/i)).toBeInTheDocument();
    expect(screen.getByAltText(/side candidate 2/i)).toBeInTheDocument();
    expect(screen.getByAltText(/back candidate 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Created my_character/i)).toBeInTheDocument();
  });
});
