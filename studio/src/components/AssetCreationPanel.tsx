import type { CandidateRun, CreateAssetResponse, ViewAssignments, ViewSelectionMode } from "../types/studio";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

interface AssetCreationPanelProps {
  assetId: string;
  candidateRun: CandidateRun | null;
  assignments: ViewAssignments;
  selectionMode: ViewSelectionMode;
  warnings?: string[];
  isCreating?: boolean;
  result?: CreateAssetResponse | null;
  error?: string | null;
  isBuilding?: boolean;
  onAssetIdChange: (assetId: string) => void;
  onGenerateAssetId: () => void;
  onSelectionModeChange: (mode: ViewSelectionMode) => void;
  onCreate: () => void;
  onCreateAndBuild?: () => void;
}

const roles = ["front", "side", "back"] as const;
const ASSET_ID_PATTERN = /^[a-z0-9_]+$/;

export function AssetCreationPanel({
  assetId,
  candidateRun,
  assignments,
  selectionMode,
  warnings = [],
  isCreating = false,
  result,
  error,
  isBuilding = false,
  onAssetIdChange,
  onGenerateAssetId,
  onSelectionModeChange,
  onCreate,
  onCreateAndBuild
}: AssetCreationPanelProps) {
  const assetIdValid = ASSET_ID_PATTERN.test(assetId);
  const hasFront = assignments.front != null;
  const hasSide = assignments.side != null;
  const hasBack = assignments.back != null;
  const duplicateIds = duplicatedAssignmentIds(assignments);
  const strictReady = hasFront && hasSide && hasBack;
  const busy = isCreating || isBuilding;
  const canCreate = Boolean(candidateRun && assetIdValid && !busy && (selectionMode === "strict" ? strictReady : hasFront));
  const hasDuplicateAssignment = duplicateIds.size > 0;

  return (
    <Panel
      title="Create Asset"
      subtitle="Authoritative view selection"
      actions={result ? <StatusBadge status="PASS" /> : null}
    >
      <div className="space-y-3">
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <label className="studio-readout block text-[10px] uppercase text-studio-muted" htmlFor="asset-id">
              asset_id
            </label>
            <button
              type="button"
              onClick={onGenerateAssetId}
              className="studio-readout border border-studio-border bg-studio-panelAlt px-2 py-1 text-[9px] font-black uppercase text-studio-muted hover:border-studio-cyan hover:text-studio-text"
            >
              New ID
            </button>
          </div>
          <input
            id="asset-id"
            value={assetId}
            onChange={(event) => onAssetIdChange(event.target.value)}
            className="studio-readout w-full border border-studio-border bg-studio-panelAlt px-2 py-2 text-xs text-studio-text outline-none focus:border-studio-accent"
            placeholder="my_character"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          {(["strict", "prototype"] as const).map((modeOption) => (
            <button
              key={modeOption}
              type="button"
              onClick={() => onSelectionModeChange(modeOption)}
              className={`studio-readout border px-2 py-2 text-[10px] font-black uppercase ${
                selectionMode === modeOption
                  ? "border-studio-accent bg-studio-accent/20 text-studio-text"
                  : "border-studio-border bg-studio-panelAlt text-studio-muted"
              }`}
            >
              {modeOption}
            </button>
          ))}
        </div>

        <div className="grid min-w-0 grid-cols-3 gap-2">
          {roles.map((role) => (
            <div key={role} className="min-w-0 overflow-hidden border border-studio-border bg-studio-panelAlt px-2 py-1">
              <span className="studio-readout text-[10px] uppercase text-studio-muted">{role}: </span>
              <span className="studio-readout text-[10px] text-studio-text">
                {assignments[role] == null ? "missing" : `candidate ${assignments[role]}`}
              </span>
            </div>
          ))}
        </div>

        <div className="space-y-1 text-[10px]">
          {!assetIdValid ? <Warning text="Asset id must be lowercase letters, numbers, and underscore only." /> : null}
          {!hasFront ? <Warning text="Front view is required." /> : null}
          {selectionMode === "strict" && !hasSide ? <Warning text="Side view is required in strict mode." /> : null}
          {selectionMode === "strict" && !hasBack ? <Warning text="Back view is required in strict mode." /> : null}
          {hasDuplicateAssignment ? <Warning text="Same candidate used for multiple views." /> : null}
          {warnings.map((warning) => (
            <Warning key={warning} text={warning} />
          ))}
        </div>

        <div className="grid grid-cols-[1fr_1.35fr] gap-2">
          <button
            type="button"
            onClick={onCreate}
            disabled={!canCreate}
            className="studio-readout border border-studio-border bg-studio-panelAlt px-3 py-2 text-[10px] font-black uppercase text-studio-muted hover:border-studio-cyan hover:text-studio-text disabled:cursor-not-allowed disabled:border-studio-border disabled:text-studio-muted"
          >
            {isCreating ? "Creating..." : "Create Only"}
          </button>
          <button
            type="button"
            onClick={onCreateAndBuild}
            disabled={!canCreate || !onCreateAndBuild}
            className="studio-readout border border-studio-accent bg-studio-accent px-3 py-2 text-xs font-black uppercase text-black disabled:cursor-not-allowed disabled:border-studio-border disabled:bg-studio-panelAlt disabled:text-studio-muted"
          >
            {isCreating ? "Creating..." : isBuilding ? "Building..." : "Create & Build"}
          </button>
        </div>

        {result ? (
          <div className="studio-readout border border-studio-pass/70 bg-studio-pass/10 p-2 text-[10px] text-studio-pass">
            Created {result.asset_id} at {result.asset_dir}
            {result.view_selection_path ? <div>View selection: {result.view_selection_path}</div> : null}
          </div>
        ) : null}
        {error ? (
          <div className="studio-readout border border-studio-fail/70 bg-studio-fail/10 p-2 text-[10px] text-studio-fail">
            {error}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function Warning({ text }: { text: string }) {
  return <p className="studio-readout text-studio-warn">{text}</p>;
}

function duplicatedAssignmentIds(assignments: ViewAssignments): Set<number> {
  const counts = new Map<number, number>();
  for (const value of Object.values(assignments)) {
    if (value == null) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([candidateId]) => candidateId));
}
