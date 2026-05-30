import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { AssetBrowser } from "@/components/spritespatial/AssetBrowser";
import { SpriteViewer } from "@/components/spritespatial/SpriteViewer";
import { PresetControls } from "@/components/spritespatial/PresetControls";
import { MeshViewer } from "@/components/spritespatial/MeshViewer";
import { ValidationPanel } from "@/components/spritespatial/ValidationPanel";
import { DiffSummary } from "@/components/spritespatial/DiffSummary";
import { RunHistory } from "@/components/spritespatial/RunHistory";
import { MOCK_ASSETS, MOCK_VALIDATION } from "@/lib/spritespatial-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "SpriteSpatial Editor" },
      {
        name: "description",
        content:
          "SpriteSpatial — desktop-style editor for sprite-to-mesh reconstruction, presets, and validation.",
      },
      { property: "og:title", content: "SpriteSpatial Editor" },
      {
        property: "og:description",
        content:
          "Desktop-style editor for sprite-to-mesh reconstruction, presets, and validation.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  const [selectedAsset, setSelectedAsset] = useState(MOCK_ASSETS[0].id);

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      {/* Title bar — Y2K chrome */}
      <header className="y2k-chrome y2k-bevel relative flex h-10 shrink-0 items-center justify-between border-b-2 border-border px-3">
        <div className="flex items-center gap-3">
          <div className="y2k-holo flex h-7 w-7 items-center justify-center border-2 border-border font-display text-[16px] leading-none text-primary-foreground y2k-glow-magenta">
            S
          </div>
          <h1 className="font-display text-[18px] leading-none text-[oklch(0.18_0.05_295)]">
            SpriteSpatial<span className="ml-1 font-fighter text-[14px] text-accent y2k-text-glow-magenta">™</span>
          </h1>
          <nav className="ml-3 flex items-center gap-0.5 font-pixel text-[12px]">
            {["File", "Edit", "View", "Run", "Help"].map((m) => (
              <span
                key={m}
                className="cursor-pointer border border-transparent px-2 py-1 hover:border-border hover:bg-[oklch(0.85_0.05_295)]"
              >
                {m}
              </span>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 font-pixel text-[11px] tracking-wider">
          <span className="flex items-center gap-1.5">
            <span className="y2k-blink h-2 w-2 border border-border bg-success y2k-glow-cyan" />
            <span className="text-[oklch(0.2_0.05_295)]">SYS · ONLINE</span>
          </span>
          <span className="font-fighter border-2 border-border bg-accent px-2 py-0.5 text-[12px] text-accent-foreground y2k-glow-magenta">
            MOCK MODE
          </span>
        </div>
      </header>

      {/* Main grid */}
      <main className="grid min-h-0 flex-1 grid-rows-[minmax(180px,1fr)_minmax(280px,1.6fr)_minmax(180px,1fr)] gap-1 p-1 lg:grid-rows-[minmax(220px,1fr)_minmax(0,2fr)_minmax(220px,1fr)]">
        {/* Top row */}
        <section className="grid min-h-0 grid-cols-1 gap-1 md:grid-cols-[260px_1fr_300px]">
          <AssetBrowser
            assets={MOCK_ASSETS}
            selectedId={selectedAsset}
            onSelect={setSelectedAsset}
          />
          <SpriteViewer assetId={selectedAsset} />
          <PresetControls />
        </section>

        {/* Middle row - mesh */}
        <section className="min-h-0">
          <MeshViewer />
        </section>

        {/* Bottom row */}
        <section className="grid min-h-0 grid-cols-1 gap-1 md:grid-cols-3">
          <ValidationPanel validation={MOCK_VALIDATION} />
          <DiffSummary />
          <RunHistory />
        </section>
      </main>

      {/* Status bar — CRT readout */}
      <footer className="y2k-chrome relative flex h-7 shrink-0 items-center justify-between gap-3 overflow-hidden border-t-2 border-border px-3 font-hud text-[12px] uppercase tracking-wider">
        <span className="flex items-center gap-2">
          <span className="font-pixel border border-border bg-primary px-1.5 py-0.5 text-[11px] text-primary-foreground">
            ASSET
          </span>
          <span className="text-[oklch(0.18_0.05_295)]">{selectedAsset}</span>
        </span>
        <span className="flex-1 overflow-hidden">
          <span className="y2k-marquee text-[oklch(0.25_0.08_295)]">
            ★ SPRITESPATIAL v0.1 ★ FRONTEND ONLY BUILD ★ READY 4 BACKEND HOOKUP ★ STAY RAD ★ Y2K READY ★
          </span>
        </span>
        <span className="text-[oklch(0.18_0.05_295)]">FPS 60 · MEM 4.2M</span>
      </footer>
      {/* Global CRT scanlines overlay */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-50 mix-blend-overlay opacity-30"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent 0px, transparent 2px, oklch(0 0 0 / 0.35) 2px, oklch(0 0 0 / 0.35) 3px)",
        }}
      />
      {/* Vignette */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-40"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 55%, oklch(0 0 0 / 0.55) 100%)",
        }}
      />
    </div>
  );
}
