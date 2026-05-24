import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);
const eegFixture = path.join(
  repoRoot,
  "tests",
  "fixtures",
  "eeg",
  "sample_resting_raw.fif",
);
const eventFixture = path.join(
  repoRoot,
  "tests",
  "fixtures",
  "events",
  "psychopy_minimal.csv",
);

test("uploads, validates, and completes preprocessing from the browser UI", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText("Study Setup")).toBeVisible();

  await page.getByTestId("project-name-input").fill("Phase 2 E2E Project");
  await page.getByTestId("create-project-button").click();
  await expect(page.getByText("Project created.")).toBeVisible();

  await page.getByTestId("experiment-name-input").fill("Oddball E2E");
  await page.getByTestId("create-experiment-button").click();
  await expect(page.getByText("Experiment created.")).toBeVisible();

  await page.getByTestId("dataset-participant-input").fill("sub-e2e");
  await page.getByTestId("dataset-session-input").fill("ses-e2e");
  await page.getByTestId("create-dataset-button").click();
  await expect(page.getByText("Dataset created.")).toBeVisible();

  await page.getByTestId("eeg-file-input").setInputFiles(eegFixture);
  await page.getByTestId("upload-eeg-button").click();
  await expect(page.getByText("EEG file uploaded.")).toBeVisible();

  await page.getByTestId("event-file-input").setInputFiles(eventFixture);
  await page.getByTestId("upload-events-button").click();
  await expect(page.getByText("Event log uploaded.")).toBeVisible();

  await expect(page.getByTestId("mapping-onset_seconds-select")).toHaveValue(
    "onset",
  );
  await page.getByTestId("save-mapping-button").click();
  await expect(page.getByText("Event mapping saved.")).toBeVisible();

  await page.getByTestId("validate-dataset-button").click();
  await expect(page.getByText("Dataset is valid.")).toBeVisible();
  await expect(page.getByText("Dataset is ready for preprocessing.")).toBeVisible();

  await page.getByTestId("resample-hz-input").fill("50");
  await expect(page.getByTestId("resample-hz-input")).toHaveValue("50");
  await page.waitForTimeout(250);
  await page.getByTestId("start-preprocessing-button").click();
  await expect(page.getByText(/Preprocessing run .* queued\./)).toBeVisible();

  await expect(page.getByTestId("preprocessing-runs")).toContainText(
    "completed",
    {
      timeout: 60_000,
    },
  );
  await expect(page.getByTestId("preprocessing-runs")).toContainText("50.0 Hz");
});
