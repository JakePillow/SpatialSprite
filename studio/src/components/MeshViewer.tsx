import { Box, Eye, RotateCcw, SquareCode } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Panel } from "./Panel";

type CameraView = "front" | "side" | "back";

interface MeshViewerProps {
  selectedRunId?: string;
  mode?: "LIVE" | "MOCK";
}

export function MeshViewer({ selectedRunId, mode = "MOCK" }: MeshViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const meshRef = useRef<THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial> | null>(null);
  const [wireframe, setWireframe] = useState(false);

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

    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(3.8, 2.4, 4.8);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.className = "h-full w-full";
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controlsRef.current = controls;

    const cube = new THREE.Mesh(
      new THREE.BoxGeometry(1.8, 2.4, 1.25),
      new THREE.MeshStandardMaterial({
        color: "#5aa9ff",
        roughness: 0.9,
        metalness: 0,
        wireframe
      })
    );
    cube.rotation.y = -0.25;
    meshRef.current = cube;
    scene.add(cube);

    const edgeLines = new THREE.LineSegments(
      new THREE.EdgesGeometry(cube.geometry),
      new THREE.LineBasicMaterial({ color: "#101114" })
    );
    cube.add(edgeLines);

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
      cube.geometry.dispose();
      cube.material.dispose();
      mount.removeChild(renderer.domElement);
      cameraRef.current = null;
      controlsRef.current = null;
      meshRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (meshRef.current) {
      meshRef.current.material.wireframe = wireframe;
      meshRef.current.material.needsUpdate = true;
    }
  }, [wireframe]);

  return (
    <Panel
      title="Mesh Preview"
      subtitle={selectedRunId ? "Run selected: mesh unavailable, showing placeholder" : "No run selected, placeholder preview"}
      actions={
        <>
          <button
            type="button"
            onClick={() => setWireframe((current) => !current)}
            title="Toggle wireframe"
            aria-label="Toggle wireframe"
            aria-pressed={wireframe}
            className={`border px-2 py-1 text-xs ${
              wireframe
                ? "border-studio-accent bg-studio-accent/20 text-studio-text"
                : "border-studio-border bg-studio-panelAlt text-studio-muted hover:text-studio-text"
            }`}
          >
            <SquareCode size={15} aria-hidden="true" />
          </button>
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
        </>
      }
      className="min-h-0"
    >
      <div className="relative h-full min-h-[280px] border border-studio-border bg-[#0d1015]">
        <div ref={mountRef} className="h-full w-full" />
        <div className="studio-readout pointer-events-none absolute bottom-2 left-2 border border-studio-border bg-studio-panel/90 px-2 py-1 text-[10px] uppercase text-studio-muted">
          {selectedRunId ? `${mode} run selected; mesh.json API pending` : "placeholder cube"}
        </div>
      </div>
    </Panel>
  );
}
