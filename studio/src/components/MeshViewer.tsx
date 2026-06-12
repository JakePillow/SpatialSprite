import { Box, Eye, RotateCcw, SquareCode } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { BuildJob } from "../types/studio";
import { Panel } from "./Panel";
import { fileUrl } from "../api/sheets";
import { buildMeshGeometry } from "../lib/buildMeshGeometry";

type CameraView = "front" | "side" | "back";
type MeshViewMode = "SOLID" | "WIREFRAME" | "VERTEX_COLOR";
type MeshStatus = "idle" | "loading" | "loaded" | "no-mesh" | "failed";

interface MeshViewerProps {
  job?: BuildJob | null;
  mode?: "LIVE" | "MOCK";
}

interface MeshArtifactSelection {
  key: string;
  path: string;
}

interface MeshStats {
  vertices: number;
  faces: number;
}

export function MeshViewer({ job, mode = "MOCK" }: MeshViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const placeholderRef = useRef<THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial> | null>(null);
  const loadedMeshRef = useRef<THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | null>(null);
  const [viewMode, setViewMode] = useState<MeshViewMode>("VERTEX_COLOR");
  const [meshStatus, setMeshStatus] = useState<MeshStatus>("idle");
  const [meshMessage, setMeshMessage] = useState<string | null>(null);
  const [meshData, setMeshData] = useState<unknown | null>(null);
  const [meshHasColors, setMeshHasColors] = useState(false);
  const [meshStats, setMeshStats] = useState<MeshStats | null>(null);

  const selectedArtifact = useMemo<MeshArtifactSelection | null>(() => {
    const artifacts = job?.artifacts;
    if (!artifacts) {
      return null;
    }
    for (const key of ["mesh", "mesh_topology_cleaned", "topological_model"]) {
      const path = artifacts[key];
      if (path) {
        return { key, path };
      }
    }
    return null;
  }, [job?.artifacts]);

  const setCameraView = useCallback((view: CameraView) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }

    const positions: Record<CameraView, [number, number, number]> = {
      front: [0, 0.4, 5],
      side: [5, 0.4, 0],
      back: [0, 0.4, -5]
    };
    camera.position.set(...positions[view]);
    camera.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.update();
  }, []);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0d1015");
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(3.8, 2.4, 4.8);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.className = "h-full w-full";
    mount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controlsRef.current = controls;

    const placeholder = new THREE.Mesh(
      new THREE.BoxGeometry(1.8, 2.4, 1.25),
      new THREE.MeshStandardMaterial({
        color: "#5aa9ff",
        roughness: 0.9,
        metalness: 0,
        wireframe: false
      })
    );
    placeholder.rotation.y = -0.25;
    placeholderRef.current = placeholder;
    scene.add(placeholder);

    const edgeLines = new THREE.LineSegments(
      new THREE.EdgesGeometry(placeholder.geometry),
      new THREE.LineBasicMaterial({ color: "#101114" })
    );
    placeholder.add(edgeLines);

    scene.add(new THREE.AmbientLight("#ffffff", 1.7));
    const keyLight = new THREE.DirectionalLight("#ffffff", 1.2);
    keyLight.position.set(3, 4, 5);
    scene.add(keyLight);

    const grid = new THREE.GridHelper(5, 10, "#34404e", "#202832");
    grid.position.y = -1.25;
    scene.add(grid);

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);

    let frame = 0;
    const render = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(render);
    };
    render();

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
      placeholder.geometry.dispose();
      placeholder.material.dispose();
      if (loadedMeshRef.current) {
        loadedMeshRef.current.geometry.dispose();
        loadedMeshRef.current.material.dispose();
      }
      mount.removeChild(renderer.domElement);
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      rendererRef.current = null;
      placeholderRef.current = null;
      loadedMeshRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!job || job.status !== "completed") {
      setMeshStatus("idle");
      setMeshMessage(null);
      setMeshData(null);
      setMeshHasColors(false);
      setMeshStats(null);
      return;
    }

    if (!selectedArtifact) {
      setMeshStatus("no-mesh");
      setMeshMessage("No mesh artifact is available for this completed run.");
      setMeshData(null);
      setMeshHasColors(false);
      setMeshStats(null);
      return;
    }

    setMeshStatus("loading");
    setMeshMessage(`Fetching ${selectedArtifact.key}: ${selectedArtifact.path}`);
    setMeshData(null);
    setMeshHasColors(false);
    setMeshStats(null);

    fetch(fileUrl(selectedArtifact.path))
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Unable to fetch mesh artifact: ${response.statusText}`);
        }
        return response.json();
      })
      .then((data) => {
        setMeshData(data);
        setMeshHasColors(meshJsonHasColors(data));
        setMeshStatus("loaded");
        setMeshMessage("Mesh loaded.");
      })
      .catch((error) => {
        setMeshStatus("failed");
        setMeshMessage(error instanceof Error ? error.message : String(error));
        setMeshData(null);
        setMeshHasColors(false);
      });
  }, [job?.job_id, job?.status, selectedArtifact]);

  const [meshGeometry, setMeshGeometry] = useState<THREE.BufferGeometry | null>(null);

  useEffect(() => {
    if (meshStatus !== "loaded" || !meshData) {
      setMeshGeometry(null);
      setMeshStats(null);
      return;
    }
    try {
      const geometry = buildMeshGeometry(meshData);
      centerAndScaleGeometry(geometry);
      const vertexCount = geometry.getAttribute("position")?.count ?? 0;
      const faceCount = geometry.index ? geometry.index.count / 3 : vertexCount / 3;
      setMeshStats({ vertices: vertexCount, faces: faceCount });
      setMeshGeometry(geometry);
    } catch (error) {
      setMeshGeometry(null);
      setMeshStats(null);
      setMeshStatus("failed");
      setMeshMessage(error instanceof Error ? error.message : "Unable to parse mesh data.");
    }
  }, [meshData, meshStatus]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) {
      return;
    }

    const placeholder = placeholderRef.current;
    const existing = loadedMeshRef.current;

    if (meshGeometry) {
      if (placeholder && scene.children.includes(placeholder)) {
        scene.remove(placeholder);
      }
      if (existing) {
        existing.geometry.dispose();
        existing.material.dispose();
        scene.remove(existing);
      }

      const material = new THREE.MeshStandardMaterial({
        color: "#8dadea",
        roughness: 0.65,
        metalness: 0.1,
        side: THREE.DoubleSide,
        wireframe: viewMode === "WIREFRAME",
        vertexColors: viewMode === "VERTEX_COLOR" && meshHasColors
      });
      const mesh = new THREE.Mesh(meshGeometry, material);
      mesh.position.set(0, 0, 0);
      loadedMeshRef.current = mesh;
      scene.add(mesh);
      setCameraView("front");
    } else {
      if (existing) {
        existing.geometry.dispose();
        existing.material.dispose();
        scene.remove(existing);
        loadedMeshRef.current = null;
      }
      if (placeholder && !scene.children.includes(placeholder)) {
        scene.add(placeholder);
      }
    }
  }, [meshGeometry, viewMode, meshHasColors, setCameraView]);

  useEffect(() => {
    if (!loadedMeshRef.current) {
      return;
    }
    loadedMeshRef.current.material.wireframe = viewMode === "WIREFRAME";
    loadedMeshRef.current.material.vertexColors = viewMode === "VERTEX_COLOR" && meshHasColors;
    loadedMeshRef.current.material.needsUpdate = true;
  }, [viewMode, meshHasColors]);

  const statusLabel = useMemo(() => {
    if (meshStatus === "loading") {
      return "Loading Mesh...";
    }
    if (meshStatus === "no-mesh") {
      return "No Mesh Available";
    }
    if (meshStatus === "failed") {
      return `Mesh Load Failed: ${meshMessage}`;
    }
    if (meshStatus === "loaded") {
      if (viewMode === "VERTEX_COLOR") {
        return meshHasColors ? "Vertex Color mode" : "Vertex Color unavailable";
      }
      return viewMode === "WIREFRAME" ? "Wireframe mode" : "Solid mode";
    }
    return job ? "Completed run selected; waiting for mesh" : "No run selected";
  }, [job, meshStatus, meshMessage, viewMode, meshHasColors]);

  const viewModeButtons = ["SOLID", "WIREFRAME", "VERTEX_COLOR"] as const;

  return (
    <Panel
      title="Mesh Preview"
      subtitle={job ? `Run selected: ${job.job_id}` : "No build run selected"}
      actions={
        <div className="flex flex-wrap gap-1">
          {viewModeButtons.map((modeOption) => (
            <button
              key={modeOption}
              type="button"
              onClick={() => setViewMode(modeOption)}
              title={modeOption}
              aria-label={modeOption}
              aria-pressed={viewMode === modeOption}
              className={`border px-2 py-1 text-xs ${
                viewMode === modeOption
                  ? "border-studio-accent bg-studio-accent/20 text-studio-text"
                  : "border-studio-border bg-studio-panelAlt text-studio-muted hover:text-studio-text"
              }`}
            >
              {modeOption}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setCameraView("front")}
            title="Front view"
            aria-label="Front view"
            className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-xs text-studio-muted hover:text-studio-text"
          >
            <Eye size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setCameraView("side")}
            title="Side view"
            aria-label="Side view"
            className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-xs text-studio-muted hover:text-studio-text"
          >
            <Box size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setCameraView("back")}
            title="Back view"
            aria-label="Back view"
            className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-xs text-studio-muted hover:text-studio-text"
          >
            <RotateCcw size={15} aria-hidden="true" />
          </button>
        </div>
      }
      className="min-h-0"
    >
      <div className="relative h-full min-h-[280px] border border-studio-border bg-[#0d1015]">
        <div ref={mountRef} className="h-full w-full" />
        <div className="studio-readout pointer-events-none absolute bottom-2 left-2 max-w-[min(32rem,calc(100%-1rem))] border border-studio-border bg-studio-panel/90 px-2 py-1 text-[10px] uppercase text-studio-muted">
          <p className={meshStatus === "failed" ? "text-studio-fail" : "text-studio-muted"}>{statusLabel}</p>
          <dl className="mt-1 grid grid-cols-[92px_1fr] gap-x-2 gap-y-0.5 normal-case">
            <DebugRow label="job" value={job?.job_id ?? "none"} />
            <DebugRow label="artifact" value={selectedArtifact ? selectedArtifact.key : "none"} />
            <DebugRow label="path" value={selectedArtifact?.path ?? "none"} />
            <DebugRow label="fetch" value={meshStatus} />
            <DebugRow label="parse" value={meshGeometry ? "parsed" : meshStatus === "failed" ? "failed" : "pending"} />
            <DebugRow label="message" value={meshMessage ?? "none"} />
            <DebugRow label="vertices" value={meshStats ? String(meshStats.vertices) : "0"} />
            <DebugRow label="faces" value={meshStats ? String(meshStats.faces) : "0"} />
            <DebugRow label="mode" value={viewMode} />
          </dl>
        </div>
      </div>
    </Panel>
  );
}

function DebugRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-studio-muted">{label}</dt>
      <dd className="truncate text-studio-text">{value}</dd>
    </>
  );
}

function meshJsonHasColors(data: unknown): boolean {
  if (!data || typeof data !== "object") {
    return false;
  }
  const body = data as { colors?: unknown; mesh?: { colors?: unknown } };
  return Array.isArray(body.colors) || Array.isArray(body.mesh?.colors);
}

function centerAndScaleGeometry(geometry: THREE.BufferGeometry) {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox;
  if (!box) {
    return;
  }
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  box.getCenter(center);
  box.getSize(size);
  geometry.translate(-center.x, -center.y, -center.z);
  const maxDimension = Math.max(size.x, size.y, size.z);
  if (maxDimension > 0) {
    geometry.scale(2.6 / maxDimension, 2.6 / maxDimension, 2.6 / maxDimension);
  }
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
}
