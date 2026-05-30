import { useCallback, useState } from "react";
import { studioApi } from "../api/studioApi";
import type { StudioMode } from "../types/studio";

export function shouldForceMocks(): boolean {
  return String(import.meta.env.VITE_STUDIO_USE_MOCKS || "").toLowerCase() === "true";
}

export function useStudioApi() {
  const [mode, setMode] = useState<StudioMode>(shouldForceMocks() ? "MOCK" : "MOCK");
  const [apiStatusMessage, setApiStatusMessage] = useState("Checking Studio API...");

  const checkBackend = useCallback(async () => {
    if (shouldForceMocks()) {
      setMode("MOCK");
      setApiStatusMessage("Mock mode forced by VITE_STUDIO_USE_MOCKS.");
      return false;
    }
    try {
      await studioApi.health();
      setMode("LIVE");
      setApiStatusMessage("Connected to local Studio API.");
      return true;
    } catch (error) {
      setMode("MOCK");
      setApiStatusMessage(error instanceof Error ? `Studio API unavailable: ${error.message}` : "Studio API unavailable.");
      return false;
    }
  }, []);

  return {
    mode,
    setMode,
    apiStatusMessage,
    setApiStatusMessage,
    checkBackend
  };
}
