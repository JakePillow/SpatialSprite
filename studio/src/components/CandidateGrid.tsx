import type { CandidateRecord, ViewAssignments, ViewRole } from "../types/studio";
import { Panel } from "./Panel";

interface CandidateGridProps {
  candidates: CandidateRecord[];
  selectedCandidateId?: number | null;
  assignments: ViewAssignments;
  activeViewRole?: ViewRole;
  imageUrlForCandidate: (candidate: CandidateRecord) => string;
  onSelectCandidate: (candidate: CandidateRecord) => void;
}

const roles: ViewRole[] = ["front", "side", "back"];

export function CandidateGrid({
  candidates,
  selectedCandidateId,
  assignments,
  activeViewRole = "front",
  imageUrlForCandidate,
  onSelectCandidate
}: CandidateGridProps) {
  const roleByCandidate = new Map<number, ViewRole[]>();
  for (const role of roles) {
    const candidateId = assignments[role];
    if (candidateId == null) {
      continue;
    }
    roleByCandidate.set(candidateId, [...(roleByCandidate.get(candidateId) ?? []), role]);
  }

  return (
    <Panel title="Candidate Review" subtitle={`${candidates.length} extracted / active ${activeViewRole}`}>
      {candidates.length === 0 ? (
        <p className="studio-readout text-[11px] text-studio-muted">Extract candidates to review crops.</p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(92px,1fr))] gap-2">
          {candidates.map((candidate) => {
            const selected = candidate.candidate_id === selectedCandidateId;
            const assignedRoles = roleByCandidate.get(candidate.candidate_id) ?? [];
            return (
              <button
                key={candidate.candidate_id}
                type="button"
                onClick={() => onSelectCandidate(candidate)}
                className={`relative flex h-28 min-w-0 flex-col border bg-studio-panelAlt p-1 text-left ${
                  selected ? "border-studio-accent text-studio-text" : "border-studio-border text-studio-muted"
                }`}
              >
                <span className="studio-readout absolute left-1 top-1 bg-black/70 px-1 text-[9px] text-studio-text">
                  id {candidate.candidate_id}
                </span>
                {assignedRoles.length > 0 ? (
                  <span className="studio-readout absolute right-1 top-1 bg-studio-accent px-1 text-[8px] font-black text-black">
                    {assignedRoles.join("/").toUpperCase()}
                  </span>
                ) : null}
                <span className="studio-grid-bg flex min-h-0 flex-1 items-center justify-center">
                  <img
                    src={imageUrlForCandidate(candidate)}
                    alt={`candidate ${candidate.candidate_id}`}
                    className="max-h-16 max-w-full object-contain [image-rendering:pixelated]"
                  />
                </span>
                <span className="studio-readout mt-1 truncate text-[9px] uppercase text-studio-text">
                  {candidate.size ? `${candidate.size[0]}x${candidate.size[1]}` : "size ?"}
                </span>
                <span className="studio-readout truncate text-[8px] uppercase">
                  {candidate.bbox ? `bbox ${candidate.bbox.join(",")}` : candidate.deterministic_pose_hint ?? "candidate"}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
