import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { BuildJob } from "../types/studio";

const completedJob: BuildJob = {
  job_id: "build_001",
  asset_id: "hero",
  status: "completed",
  artifacts: {
    mesh: "outputs/studio_builds/build_001/mesh.json",
    topological_model: "outputs/studio_builds/build_001/topological_model.json"
  }
};

let MeshViewer: typeof import("./MeshViewer").MeshViewer;

describe("MeshViewer", () => {
  beforeAll(async () => {
    vi.doMock("three", async (importOriginal) => {
      const actual = await importOriginal<typeof import("three")>();
      return {
        ...actual,
        WebGLRenderer: class {
          domElement = document.createElement("canvas");
          setPixelRatio = () => undefined;
          setSize = () => undefined;
          render = () => undefined;
          dispose = () => undefined;
        }
      };
    });
    vi.doMock("three/examples/jsm/controls/OrbitControls.js", () => ({
      OrbitControls: class {
        enableDamping = false;
        dampingFactor = 0;
        target = { set: () => undefined };
        update = () => undefined;
        dispose = () => undefined;
      }
    }));
    MeshViewer = (await import("./MeshViewer")).MeshViewer;
  });

  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = vi.fn();
        disconnect = vi.fn();
      }
    );
    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows unavailable state when no job is selected", () => {
    render(<MeshViewer job={null} />);

    expect(screen.getByText("No run selected")).toBeInTheDocument();
    expect(screen.getByText("job")).toBeInTheDocument();
    expect(screen.getAllByText("none").length).toBeGreaterThanOrEqual(1);
  });

  it("shows no mesh available for a completed job without mesh artifacts", async () => {
    render(<MeshViewer job={{ ...completedJob, artifacts: {} }} />);

    await waitFor(() => expect(screen.getByText("No Mesh Available")).toBeInTheDocument());
    expect(screen.getByText("No mesh artifact is available for this completed run.")).toBeInTheDocument();
  });

  it("fetches a completed job mesh artifact", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          vertices: [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0]
          ],
          indices: [0, 1, 2]
        })
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MeshViewer job={completedJob} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toContain("path=outputs%2Fstudio_builds%2Fbuild_001%2Fmesh.json");
  });

  it("shows fetch failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        statusText: "Not Found"
      })
    );

    render(<MeshViewer job={completedJob} />);

    await waitFor(() => expect(screen.getByText(/Mesh Load Failed/i)).toBeInTheDocument());
    expect(screen.getAllByText(/Unable to fetch mesh artifact: Not Found/i).length).toBeGreaterThan(0);
  });

  it("shows parsed vertex and face counts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            vertices: [
              [0, 0, 0],
              [1, 0, 0],
              [1, 1, 0],
              [0, 1, 0]
            ],
            faces: [[0, 1, 2, 3]],
            colors: [
              [1, 0, 0, 1],
              [0, 1, 0, 1],
              [0, 0, 1, 1],
              [1, 1, 1, 1]
            ]
          })
      })
    );

    render(<MeshViewer job={completedJob} />);

    await waitFor(() => expect(screen.getByText("Vertex Color mode")).toBeInTheDocument());
    expect(screen.getByText("vertices")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("faces")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
