import type { CandidateRecord, ViewAssignments, ViewRole } from "../types/studio";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

interface ViewAssignmentPanelProps {
  candidates: CandidateRecord[];
  selectedCandidate?: CandidateRecord | null;
  assignments: ViewAssignments;
  activeViewRole: ViewRole;
  imageUrlForCandidate: (candidate: CandidateRecord) => string;
  onActiveViewChange: (role: ViewRole) => void;
  onAssign: (role: ViewRole, candidateId: number) => void;
  onClear: (role: ViewRole) => void;
}

const roles: ViewRole[] = ["front", "side", "back"];

export function ViewAssignmentPanel({
  candidates,
  selectedCandidate,
  assignments,
  activeViewRole,
  imageUrlForCandidate,
  onActiveViewChange,
  onAssign,
  onClear
}: ViewAssignmentPanelProps) {
  const candidateById = new Map(candidates.map((candidate) => [candidate.candidate_id, candidate]));
  const duplicateIds = duplicatedAssignmentIds(assignments);

  return (
    <Panel
      title="View Selection Workflow"
      subtitle={selectedCandidate ? `selected candidate ${selectedCandidate.candidate_id}` : "select a candidate"}
    >
      <div className="space-y-3">
        <div className="grid min-w-0 grid-cols-[repeat(5,minmax(0,1fr))] gap-1">
          {roles.map((role, index) => (
            <button
              key={role}
              type="button"
              onClick={() => onActiveViewChange(role)}
              className={`studio-readout min-w-0 truncate border px-1 py-1 text-[9px] font-black uppercase ${
                activeViewRole === role
                  ? "border-studio-accent bg-studio-accent/20 text-studio-text"
                  : "border-studio-border bg-studio-panelAlt text-studio-muted"
              }`}
            >
              {index + 1}. {role}
            </button>
          ))}
          <button
            type="button"
            onClick={() => selectedCandidate && onAssign(activeViewRole, selectedCandidate.candidate_id)}
            disabled={!selectedCandidate}
            className="studio-readout min-w-0 truncate border border-studio-cyan bg-studio-cyan/15 px-1 py-1 text-[9px] font-black uppercase text-studio-cyan disabled:cursor-not-allowed disabled:border-studio-border disabled:text-studio-muted"
          >
            assign
          </button>
          <button
            type="button"
            onClick={() => onClear(activeViewRole)}
            className="studio-readout min-w-0 truncate border border-studio-border bg-studio-panelAlt px-1 py-1 text-[9px] font-black uppercase text-studio-muted"
          >
            reset
          </button>
        </div>

        <div className="grid min-w-0 grid-cols-3 gap-2">
          {roles.map((role) => {
            const candidateId = assignments[role];
            const candidate = candidateId == null ? undefined : candidateById.get(candidateId);
            const authority = candidate == null ? "missing" : duplicateIds.has(candidate.candidate_id) ? "placeholder" : "authored";
            return (
              <div key={role} className="min-w-0 overflow-hidden border border-studio-border bg-studio-panelAlt p-2">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="studio-readout min-w-0 truncate text-[10px] font-black uppercase text-studio-text">{role}</span>
                  <StatusBadge status={authority === "missing" ? "WARNING" : authority === "placeholder" ? "WARNING" : "PASS"} />
                </div>
                <div className="studio-grid-bg mb-2 flex h-20 items-center justify-center border border-studio-border bg-black/30">
                  {candidate ? (
                    <img
                      src={imageUrlForCandidate(candidate)}
                      alt={`${role} candidate ${candidate.candidate_id}`}
                      className="max-h-16 max-w-full object-contain [image-rendering:pixelated]"
                    />
                  ) : (
                    <span className="studio-readout text-[10px] text-studio-muted">missing</span>
                  )}
                </div>
                <div className="studio-readout flex min-w-0 items-center justify-between gap-1 text-[10px] text-studio-muted">
                  <span className="min-w-0 truncate">{candidate ? `candidate ${candidate.candidate_id}` : authority}</span>
                  {candidate ? (
                    <button type="button" className="text-studio-cyan hover:text-studio-text" onClick={() => onClear(role)}>
                      clear
                    </button>
                  ) : null}
                </div>
                {candidate?.size ? (
                  <div className="studio-readout mt-1 truncate text-[9px] text-studio-muted">
                    {candidate.size[0]}x{candidate.size[1]} bbox {candidate.bbox?.join(",") ?? "?"}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        <p className="studio-readout text-[9px] uppercase text-studio-muted">Shortcuts: F front / S side / B back / R reset current</p>
      </div>
    </Panel>
  );
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
