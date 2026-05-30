import type { ValidationStatus } from "../types/studio";

const statusClass: Record<ValidationStatus, string> = {
  PASS: "border-studio-pass/50 bg-studio-pass/15 text-studio-pass",
  WARNING: "border-studio-warn/50 bg-studio-warn/15 text-studio-warn",
  FAIL: "border-studio-fail/50 bg-studio-fail/15 text-studio-fail"
};

export function StatusBadge({ status }: { status: ValidationStatus }) {
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[11px] font-semibold ${statusClass[status]}`}>
      {status}
    </span>
  );
}
