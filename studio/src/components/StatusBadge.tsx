import type { ValidationStatus } from "../types/studio";

const statusClass: Record<ValidationStatus, string> = {
  PASS: "border-studio-pass/60 bg-studio-pass/15 text-studio-pass shadow-[0_0_10px_rgba(157,255,115,0.18)]",
  WARNING: "border-studio-warn/60 bg-studio-warn/15 text-studio-warn",
  FAIL: "border-studio-fail/60 bg-studio-fail/15 text-studio-fail shadow-[0_0_10px_rgba(255,92,122,0.18)]"
};

export function StatusBadge({ status }: { status: ValidationStatus }) {
  return (
    <span className={`studio-readout inline-flex border px-2 py-0.5 text-[10px] font-black ${statusClass[status]}`}>
      {status}
    </span>
  );
}
