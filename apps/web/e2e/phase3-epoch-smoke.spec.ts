import { test } from "@playwright/test";
import {
  createCompletedEpochRun,
  createPreprocessedDataset,
} from "./helpers/workflow";

test("creates an epoch run from completed preprocessing", async ({ page }) => {
  await createPreprocessedDataset(page, {
    project: "Phase 3 Epoch Project",
    experiment: "Epoch E2E",
    participant: "sub-epoch",
    session: "ses-epoch",
  });

  await createCompletedEpochRun(page);
});
