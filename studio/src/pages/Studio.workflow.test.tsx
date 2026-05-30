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

  it("applies a mock preset and updates run history, validation, and diff panels", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<Studio />);

    fireEvent.click(screen.getByRole("button", { name: /apply preset/i }));

    await waitFor(() => expect(screen.getByText(/pull_hat_back@0.75/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText(/mock_pull_hat_back/).length).toBeGreaterThan(0));
    expect(screen.getByText("hat_asymmetry +0.7")).toBeInTheDocument();
    expect(screen.getByText("validation_passed")).toBeInTheDocument();
  });
});
