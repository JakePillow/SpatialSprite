import type { RawSheet } from "../types/studio";
import { Panel } from "./Panel";

interface SourceSheetBrowserProps {
  sheets: RawSheet[];
  selectedSheetPath?: string;
  isLoading?: boolean;
  isUploading?: boolean;
  uploadDisabled?: boolean;
  uploadDisabledLabel?: string;
  uploadError?: string | null;
  imageUrlForSheet: (sheet: RawSheet) => string;
  onSelectSheet: (sheet: RawSheet) => void;
  onUploadSheet: (file: File) => void;
}

export function SourceSheetBrowser({
  sheets,
  selectedSheetPath,
  isLoading = false,
  isUploading = false,
  uploadDisabled = false,
  uploadDisabledLabel = "API Required",
  uploadError,
  imageUrlForSheet,
  onSelectSheet,
  onUploadSheet
}: SourceSheetBrowserProps) {
  return (
    <Panel
      title="Raw Sheets"
      subtitle="assets/raw"
      actions={
        <label
          className={`studio-readout border px-2 py-1 text-[10px] font-black uppercase ${
            uploadDisabled
              ? "cursor-not-allowed border-studio-border bg-studio-panelAlt text-studio-muted"
              : "cursor-pointer border-studio-cyan bg-studio-cyan/15 text-studio-cyan"
          }`}
        >
          {uploadDisabled ? uploadDisabledLabel : isUploading ? "Uploading..." : "Upload Sheet"}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            disabled={isUploading || uploadDisabled}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file) {
                onUploadSheet(file);
              }
            }}
          />
        </label>
      }
    >
      <div className="space-y-2">
        {isLoading ? <p className="studio-readout text-[11px] text-studio-muted">Loading sheets...</p> : null}
        {uploadError ? <p className="studio-readout text-[10px] text-studio-fail">{uploadError}</p> : null}
        {sheets.length === 0 && !isLoading ? (
          <p className="studio-readout text-[11px] text-studio-muted">No image sheets found.</p>
        ) : null}
        {sheets.map((sheet) => {
          const selected = sheet.path === selectedSheetPath;
          return (
            <button
              key={sheet.path}
              type="button"
              onClick={() => onSelectSheet(sheet)}
              className={`grid w-full grid-cols-[56px_1fr] gap-2 border p-2 text-left transition ${
                selected
                  ? "border-studio-accent bg-studio-accent/10 text-studio-text"
                  : "border-studio-border bg-studio-panelAlt text-studio-muted hover:border-studio-cyan hover:text-studio-text"
              }`}
            >
              <span className="studio-grid-bg flex h-12 w-14 items-center justify-center overflow-hidden border border-studio-border bg-black/40">
                <img
                  src={imageUrlForSheet(sheet)}
                  alt=""
                  className="h-full w-full object-contain [image-rendering:pixelated]"
                />
              </span>
              <span className="min-w-0">
                <span className="studio-readout block truncate text-[11px] font-black">{sheet.filename}</span>
                <span className="studio-readout mt-1 block text-[10px] uppercase text-studio-muted">
                  {sheet.width} x {sheet.height}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
