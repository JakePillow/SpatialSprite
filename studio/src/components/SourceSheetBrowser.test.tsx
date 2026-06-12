import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockRawSheets } from "../mock/studioMock";
import { SourceSheetBrowser } from "./SourceSheetBrowser";

describe("SourceSheetBrowser", () => {
  it("selects a raw sprite sheet", () => {
    const onSelectSheet = vi.fn();
    render(
      <SourceSheetBrowser
        sheets={mockRawSheets}
        selectedSheetPath=""
        imageUrlForSheet={() => "/placeholders/front.svg"}
        onSelectSheet={onSelectSheet}
        onUploadSheet={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /SNES - Super Mario World/i }));

    expect(onSelectSheet).toHaveBeenCalledWith(mockRawSheets[0]);
  });

  it("uploads a selected sheet file", () => {
    const onUploadSheet = vi.fn();
    render(
      <SourceSheetBrowser
        sheets={mockRawSheets}
        selectedSheetPath=""
        imageUrlForSheet={() => "/placeholders/front.svg"}
        onSelectSheet={vi.fn()}
        onUploadSheet={onUploadSheet}
      />
    );

    const file = new File(["sheet"], "sheet.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(/upload sheet/i), { target: { files: [file] } });

    expect(onUploadSheet).toHaveBeenCalledWith(file);
  });
});
