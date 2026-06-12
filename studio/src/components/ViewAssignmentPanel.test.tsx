import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CandidateRecord } from "../types/studio";
import { ViewAssignmentPanel } from "./ViewAssignmentPanel";

const candidate: CandidateRecord = {
  candidate_id: 7,
  path: "/placeholders/front.svg",
  deterministic_pose_hint: "front"
};

describe("ViewAssignmentPanel", () => {
  it("assigns the selected candidate to a canonical view", () => {
    const onAssign = vi.fn();
    render(
      <ViewAssignmentPanel
        candidates={[candidate]}
        selectedCandidate={candidate}
        assignments={{}}
        activeViewRole="front"
        imageUrlForCandidate={(item) => item.path}
        onActiveViewChange={vi.fn()}
        onAssign={onAssign}
        onClear={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /^assign$/i }));

    expect(onAssign).toHaveBeenCalledWith("front", 7);
  });
});
