import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BuildJob, StudioAsset } from "../types/studio";
import { BuildPanel } from "./BuildPanel";

const asset: StudioAsset = {
  id: "hero",
  coverage: "front_back",
  sprites: { front: "", back: "", side: "" }
};

describe("BuildPanel", () => {
  it("renders the build button and starts a build", () => {
    const onBuild = vi.fn();
    render(<BuildPanel asset={asset} job={null} onBuild={onBuild} />);

    fireEvent.click(screen.getByRole("button", { name: /build asset/i }));

    expect(onBuild).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /build asset/i })).toBeInTheDocument();
    expect(screen.getAllByText("hero")).toHaveLength(2);
  });

  it("renders completed validation state", () => {
    const job: BuildJob = {
      job_id: "build_001",
      asset_id: "hero",
      status: "completed",
      output_dir: "outputs/studio_builds/build_001",
      validation_report: { passed: true },
      artifacts: {}
    };
    render(<BuildPanel asset={asset} job={job} onBuild={vi.fn()} />);

    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getAllByText("PASS").length).toBeGreaterThanOrEqual(1);
  });

  it("renders failed state and error text", () => {
    const job: BuildJob = {
      job_id: "build_002",
      asset_id: "hero",
      status: "failed",
      error: "mock failure",
      artifacts: {}
    };
    render(<BuildPanel asset={asset} job={job} onBuild={vi.fn()} />);

    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("mock failure")).toBeInTheDocument();
  });
});
