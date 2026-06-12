import type { CandidateRun, RawSheet } from "../types/studio";
import { Panel } from "./Panel";

interface SourceSheetPreviewProps {
  sheet?: RawSheet;
  sheetImageUrl?: string;
  candidateRun?: CandidateRun | null;
  contactSheetUrl?: string;
  isExtracting?: boolean;
  onExtract: () => void;
}

export function SourceSheetPreview({
  sheet,
  sheetImageUrl,
  candidateRun,
  contactSheetUrl,
  isExtracting = false,
  onExtract
}: SourceSheetPreviewProps) {
  return (
    <Panel
      title="Sheet Preview"
      subtitle={sheet ? `${sheet.width} x ${sheet.height}` : "select a raw sheet"}
      actions={
        <button
          type="button"
          onClick={onExtract}
          disabled={!sheet || isExtracting}
          className="studio-readout border border-studio-cyan bg-studio-cyan/15 px-3 py-1 text-[10px] font-black uppercase text-studio-cyan disabled:cursor-not-allowed disabled:border-studio-border disabled:text-studio-muted"
        >
          {isExtracting ? "Extracting..." : "Extract Candidates"}
        </button>
      }
    >
      <div className="grid h-full min-h-0 min-w-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(220px,1fr)_minmax(220px,1fr)]">
        <div className="studio-grid-bg flex min-h-0 items-center justify-center overflow-auto border border-studio-border bg-black/40 p-3">
          {sheet && sheetImageUrl ? (
            <img
              src={sheetImageUrl}
              alt={`${sheet.filename} source sheet`}
              className="max-h-[34rem] max-w-full object-contain [image-rendering:pixelated]"
            />
          ) : (
            <p className="studio-readout text-[11px] text-studio-muted">No sheet selected.</p>
          )}
        </div>
        <div className="studio-grid-bg flex min-h-0 items-center justify-center overflow-auto border border-studio-border bg-black/40 p-3">
          {candidateRun && contactSheetUrl ? (
            <img
              src={contactSheetUrl}
              alt="Candidate contact sheet"
              className="max-h-[34rem] max-w-full object-contain [image-rendering:pixelated]"
            />
          ) : (
            <div className="studio-readout text-center text-[11px] text-studio-muted">
              <p>Candidate contact sheet appears here.</p>
              <p className="mt-1">No asset files are written in this phase.</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
