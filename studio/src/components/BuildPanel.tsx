import type { BuildJob, StudioAsset } from "../types/studio";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

interface BuildPanelProps {
  asset?: StudioAsset;
  job?: BuildJob | null;
  isStarting?: boolean;
  error?: string | null;
  onBuild: () => void;
}

export function BuildPanel({ asset, job, isStarting = false, error, onBuild }: BuildPanelProps) {
  const status = job?.status ?? "idle";
  const validationPassed = readPassed(job);
  return (
    <Panel
      title="Build Asset"
      subtitle={asset?.id ?? "no asset selected"}
      actions={job ? <StatusBadge status={job.status === "failed" ? "FAIL" : job.status === "completed" ? "PASS" : "WARNING"} /> : null}
    >
      <div className="space-y-3">
        <button
          type="button"
          onClick={onBuild}
          disabled={!asset || isStarting || status === "queued" || status === "running"}
          className="studio-readout w-full border border-studio-accent bg-studio-accent px-3 py-2 text-xs font-black uppercase text-black disabled:cursor-not-allowed disabled:border-studio-border disabled:bg-studio-panelAlt disabled:text-studio-muted"
        >
          {isStarting ? "Starting..." : "Build Asset"}
        </button>
        <Readout label="Asset" value={asset?.id ?? "none"} />
        <Readout label="Status" value={status} />
        <Readout label="Output Folder" value={job?.output_dir ?? "none"} />
        <Readout label="Validation" value={validationPassed == null ? "pending" : validationPassed ? "PASS" : "FAIL"} />
        {error ? <p className="studio-readout border border-studio-fail/70 bg-studio-fail/10 p-2 text-[10px] text-studio-fail">{error}</p> : null}
        {job?.error ? <p className="studio-readout border border-studio-fail/70 bg-studio-fail/10 p-2 text-[10px] text-studio-fail">{job.error}</p> : null}
      </div>
    </Panel>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="studio-readout grid grid-cols-[100px_1fr] gap-2 border border-studio-border bg-studio-panelAlt px-2 py-1 text-[10px]">
      <span className="uppercase text-studio-muted">{label}</span>
      <span className="truncate text-studio-text">{value}</span>
    </div>
  );
}

function readPassed(job?: BuildJob | null): boolean | null {
  const validation = job?.validation_report ?? job?.validation;
  return typeof validation?.passed === "boolean" ? validation.passed : job?.validation_passed ?? null;
}
