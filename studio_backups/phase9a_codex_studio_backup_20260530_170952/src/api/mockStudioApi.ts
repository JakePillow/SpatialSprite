import {
  mockAssets,
  mockDiffSummary,
  mockPresets,
  mockRuns,
  mockValidation
} from "../mock/studioMock";

export const mockStudioApi = {
  listAssets: () => mockAssets,
  listPresets: () => mockPresets,
  getDiffSummary: () => mockDiffSummary,
  getValidation: () => mockValidation,
  listRuns: () => mockRuns
};
