import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CandidateRecord } from "../types/studio";
import { CandidateGrid } from "./CandidateGrid";

const candidates: CandidateRecord[] = [
  { candidate_id: 0, path: "/placeholders/front.svg", deterministic_pose_hint: "front" },
  { candidate_id: 1, path: "/placeholders/back.svg", deterministic_pose_hint: "back" }
];

describe("CandidateGrid", () => {
  it("selects an extracted candidate", () => {
    const onSelectCandidate = vi.fn();
    render(
      <CandidateGrid
        candidates={candidates}
        selectedCandidateId={null}
        assignments={{}}
        imageUrlForCandidate={(candidate) => candidate.path}
        onSelectCandidate={onSelectCandidate}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /candidate 1/i }));

    expect(onSelectCandidate).toHaveBeenCalledWith(candidates[1]);
  });
});
