import type { StudioMode } from "../types/studio";

interface TopStatusBarProps {
  mode: StudioMode;
  apiStatusMessage: string;
  selectedAssetId: string;
  selectedPresetId: string;
  selectedRunId?: string;
  workflowError?: string | null;
}

export function TopStatusBar({
  mode,
  apiStatusMessage,
  selectedAssetId,
  selectedPresetId,
  selectedRunId,
  workflowError
}: TopStatusBarProps) {
  return (
    <header className="studio-chrome flex h-11 shrink-0 items-center justify-between border-2 border-studio-border px-3 text-[11px]">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-7 w-7 items-center justify-center border-2 border-studio-border bg-studio-magenta text-sm font-black text-black shadow-[var(--studio-shadow-magenta)]">
          S
        </div>
        <div className="min-w-0">
          <h1 className="studio-wordmark text-sm font-black leading-none text-studio-text">SpriteSpatial Studio</h1>
          <p className="studio-readout truncate text-[10px] text-studio-muted">
            {workflowError ? workflowError : apiStatusMessage}
          </p>
        </div>
      </div>

      <div className="studio-readout flex items-center gap-2 text-[10px] uppercase">
        <span
          className={`border px-2 py-1 font-black ${
            mode === "LIVE"
              ? "border-studio-pass bg-studio-pass/20 text-studio-pass"
              : "border-studio-warn bg-studio-warn/20 text-studio-warn"
          }`}
        >
          {mode}
        </span>
        <span className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-studio-muted">
          asset <b className="text-studio-text">{selectedAssetId}</b>
        </span>
        <span className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-studio-muted">
          preset <b className="text-studio-text">{selectedPresetId}</b>
        </span>
        <span className="border border-studio-border bg-studio-panelAlt px-2 py-1 text-studio-muted">
          run <b className="text-studio-text">{selectedRunId || "none"}</b>
        </span>
      </div>
    </header>
  );
}
