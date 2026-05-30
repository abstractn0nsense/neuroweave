import { expect, test } from "@playwright/test";
import {
  createCompletedEpochRun,
  createCompletedErpRun,
  createPreprocessedDataset,
} from "./helpers/workflow";

test.use({
  viewport: { width: 1280, height: 900 },
});

test("captures stable ERP preview and QC dashboard baselines", async ({
  page,
}) => {
  await createPreprocessedDataset(page, {
    project: "Visual Seed Project",
    experiment: "ERP Visual Seed",
    participant: "sub-visual",
    session: "ses-visual",
  });

  await createCompletedEpochRun(page);
  await createCompletedErpRun(page);

  await expect(page.getByTestId("erp-preview")).toHaveScreenshot(
    "erp-preview-seed.png",
    {
      animations: "disabled",
      maxDiffPixelRatio: 0.01,
    },
  );

  await expect(page.getByTestId("qc-dashboard")).toHaveScreenshot(
    "qc-dashboard-erp-seed.png",
    {
      animations: "disabled",
      mask: [page.locator(".qc-header span").first()],
      maxDiffPixelRatio: 0.01,
    },
  );
});
