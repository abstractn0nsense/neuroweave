import { test } from "@playwright/test";
import {
  createComparisonSummary,
  createCompletedEpochRun,
  createCompletedErpRun,
  createPreprocessedDataset,
} from "./helpers/workflow";

test("creates ERP preview and comparison summary from completed epochs", async ({
  page,
}) => {
  await createPreprocessedDataset(page, {
    project: "Phase 3 ERP Project",
    experiment: "ERP E2E",
    participant: "sub-erp",
    session: "ses-erp",
  });

  await createCompletedEpochRun(page);
  await createCompletedErpRun(page);
  await createComparisonSummary(page);
});
