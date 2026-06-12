import {
  mockAssets,
  mockBuildJobs,
  mockDiffSummary,
  mockPresets,
  mockRawSheets,
  mockRuns,
  mockValidation
} from "../mock/studioMock";

export const mockStudioApi = {
  listAssets: () => mockAssets,
  listPresets: () => mockPresets,
  listRawSheets: () => mockRawSheets,
  listBuildJobs: () => mockBuildJobs,
  getDiffSummary: () => mockDiffSummary,
  getValidation: () => mockValidation,
  listRuns: () => mockRuns
};
