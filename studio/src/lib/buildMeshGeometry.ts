import * as THREE from "three";

export interface MeshJson {
  schema?: string;
  vertices?: unknown;
  verts?: unknown;
  faces?: unknown;
  triangles?: unknown;
  indices?: unknown;
  mesh?: {
    vertices?: unknown;
    verts?: unknown;
    faces?: unknown;
    triangles?: unknown;
    indices?: unknown;
    colors?: unknown;
  };
  colors?: Array<[number, number, number] | [number, number, number, number]> | number[];
}

function isNumericArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

function isVertexArray(value: unknown): value is [number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 3 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
  );
}

function isVertexObject(value: unknown): value is { x: number; y: number; z: number } {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    ["x", "y", "z"].every((key) => {
      const entry = (value as Record<string, unknown>)[key];
      return typeof entry === "number" && Number.isFinite(entry);
    })
  );
}

function isFaceArray(value: unknown): value is number[] {
  return (
    Array.isArray(value) &&
    (value.length === 3 || value.length === 4) &&
    value.every((item) => Number.isInteger(item) && item >= 0)
  );
}

function parseVertices(value: unknown): number[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("Mesh JSON must contain a non-empty vertices array.");
  }
  const positions: number[] = [];
  for (const vertex of value) {
    if (isVertexArray(vertex)) {
      positions.push(vertex[0], vertex[1], vertex[2]);
    } else if (isVertexObject(vertex)) {
      positions.push(vertex.x, vertex.y, vertex.z);
    } else {
      throw new Error("Mesh vertices must be arrays of three finite numbers or {x,y,z} objects.");
    }
  }
  return positions;
}

function parseFaces(value: unknown): number[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("Mesh JSON must contain a non-empty faces array.");
  }
  const indices: number[] = [];
  if (isNumericArray(value)) {
    if (value.length % 3 !== 0 || !value.every((item) => Number.isInteger(item) && item >= 0)) {
      throw new Error("Mesh flat indices must be non-negative integer triples.");
    }
    return value;
  }
  for (const face of value) {
    const faceValue =
      Boolean(face) && typeof face === "object" && !Array.isArray(face) ? (face as { indices?: unknown }).indices : face;
    if (!isFaceArray(faceValue)) {
      console.warn("Ignoring unsupported mesh face.", face);
      continue;
    }
    indices.push(faceValue[0], faceValue[1], faceValue[2]);
    if (faceValue.length === 4) {
      indices.push(faceValue[0], faceValue[2], faceValue[3]);
    }
  }
  if (indices.length === 0) {
    throw new Error("Mesh JSON contains no supported triangle or quad faces.");
  }
  return indices;
}

function parseColors(value: unknown, vertexCount: number): number[] | null {
  if (value == null) {
    return null;
  }
  if (Array.isArray(value)) {
    if (value.length === vertexCount && value.every(isVertexArray)) {
      return value.flat();
    }
    if (value.length === vertexCount && value.every((item) => Array.isArray(item) && (item.length === 3 || item.length === 4) && item.every((entry) => typeof entry === "number" && Number.isFinite(entry)))) {
      return (value as Array<number[]>).flatMap((item) => [item[0], item[1], item[2]]);
    }
    if (isNumericArray(value) && value.length === vertexCount * 3) {
      return value;
    }
  }
  return null;
}

export function buildMeshGeometry(mesh: unknown): THREE.BufferGeometry {
  if (!mesh || typeof mesh !== "object") {
    throw new Error("Invalid mesh data.");
  }
  const meshJson = mesh as MeshJson;
  const meshBody = meshJson.mesh ?? meshJson;
  const positions = parseVertices(meshBody.vertices ?? meshBody.verts);
  const indices = parseFaces(meshBody.faces ?? meshBody.triangles ?? meshBody.indices);
  if (indices.length === 0) {
    throw new Error("Mesh JSON contains no triangle faces.");
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  const colors = parseColors(meshBody.colors ?? meshJson.colors, positions.length / 3);
  if (colors) {
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  }
  geometry.computeVertexNormals();
  return geometry;
}
