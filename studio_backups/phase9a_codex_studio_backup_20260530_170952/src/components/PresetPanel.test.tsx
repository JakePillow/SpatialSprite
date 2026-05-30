import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { mockPresets } from "../mock/studioMock";
import { PresetPanel } from "./PresetPanel";

describe("PresetPanel", () => {
  it("changes preset, intensity, and applies the selected preset", () => {
    const onSelectPreset = vi.fn();
    const onIntensityChange = vi.fn();
    const onApply = vi.fn();

    render(
      <PresetPanel
        presets={mockPresets}
        selectedPresetId="pull_hat_back"
        intensity={0.75}
        lastAppliedPreset={null}
        onSelectPreset={onSelectPreset}
        onIntensityChange={onIntensityChange}
        onApply={onApply}
      />
    );

    fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "thicken_torso" } });
    fireEvent.change(screen.getByLabelText("Preset intensity"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByRole("button", { name: /apply preset/i }));

    expect(onSelectPreset).toHaveBeenCalledWith("thicken_torso");
    expect(onIntensityChange).toHaveBeenCalledWith(0.5);
    expect(onApply).toHaveBeenCalledTimes(1);
  });
});
