import { expect, test } from "@playwright/test";
import { createPreprocessedDataset } from "./helpers/workflow";

test("uploads, validates, and completes preprocessing from the browser UI", async ({
  page,
}) => {
  await createPreprocessedDataset(page, {
    project: "Phase 2 E2E Project",
    experiment: "Oddball E2E",
    participant: "sub-e2e",
    session: "ses-e2e",
  });
});
