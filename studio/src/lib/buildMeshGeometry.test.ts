import { describe, expect, it, vi } from "vitest";
import { buildMeshGeometry } from "./buildMeshGeometry";

describe("buildMeshGeometry", () => {
  it("builds a simple triangle", () => {
    const geometry = buildMeshGeometry({
      vertices: [
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0]
      ],
      faces: [[0, 1, 2]]
    });

    expect(geometry.getAttribute("position").count).toBe(3);
    expect(geometry.index?.count).toBe(3);
  });

  it("triangulates quads", () => {
    const geometry = buildMeshGeometry({
      vertices: [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0]
      ],
      faces: [[0, 1, 2, 3]]
    });

    expect(Array.from(geometry.index?.array ?? [])).toEqual([0, 1, 2, 0, 2, 3]);
  });

  it("supports nested mesh schema and flat indices", () => {
    const geometry = buildMeshGeometry({
      mesh: {
        vertices: [
          { x: 0, y: 0, z: 0 },
          { x: 1, y: 0, z: 0 },
          { x: 0, y: 1, z: 0 }
        ],
        indices: [0, 1, 2]
      }
    });

    expect(geometry.getAttribute("position").count).toBe(3);
    expect(geometry.index?.count).toBe(3);
  });

  it("throws a useful error when vertices are missing", () => {
    expect(() => buildMeshGeometry({ faces: [[0, 1, 2]] })).toThrow(/vertices/i);
  });

  it("throws a useful error when faces are missing", () => {
    expect(() =>
      buildMeshGeometry({
        vertices: [
          [0, 0, 0],
          [1, 0, 0],
          [0, 1, 0]
        ]
      })
    ).toThrow(/faces/i);
  });

  it("accepts optional vertex colors", () => {
    const geometry = buildMeshGeometry({
      vertices: [
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0]
      ],
      faces: [[0, 1, 2]],
      colors: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1]
      ]
    });

    expect(geometry.getAttribute("color").count).toBe(3);
  });

  it("ignores unsupported face entries with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const geometry = buildMeshGeometry({
      vertices: [
        [0, 0, 0],
        [1, 0, 0],
        [0, 1, 0]
      ],
      faces: [[0, 1], [0, 1, 2]]
    });

    expect(warn).toHaveBeenCalled();
    expect(geometry.index?.count).toBe(3);
    warn.mockRestore();
  });
});
