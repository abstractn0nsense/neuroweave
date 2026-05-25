import { expect, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../..",
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

type WorkflowLabels = {
  project: string;
  experiment: string;
  participant: string;
  session: string;
};

export async function createPreprocessedDataset(
  page: Page,
  labels: WorkflowLabels,
) {
  await page.goto("/");
  await expect(page.getByText("Study Setup")).toBeVisible();

  await page.getByTestId("project-name-input").fill(labels.project);
  await page.getByTestId("create-project-button").click();
  await expect(page.getByText("Project created.")).toBeVisible();

  await page.getByTestId("experiment-name-input").fill(labels.experiment);
  await page.getByTestId("create-experiment-button").click();
  await expect(page.getByText("Experiment created.")).toBeVisible();

  await page.getByTestId("dataset-participant-input").fill(labels.participant);
  await page.getByTestId("dataset-session-input").fill(labels.session);
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
  await expect(page.getByTestId("stage-events-value")).toContainText(
    "normalized",
  );
  const mappedEventsText = await page
    .getByTestId("stage-events-value")
    .textContent();
  expect(mappedEventsText).not.toBe("Unmapped");

  await page.reload();
  await expect(page.getByText("Study Setup")).toBeVisible();
  await expect(page.getByTestId("stage-events-value")).toHaveText(
    mappedEventsText ?? "",
  );

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
}

export async function createCompletedEpochRun(page: Page) {
  await expect(page.getByTestId("epoch-preprocessing-run-select")).not.toHaveValue(
    "",
    { timeout: 15_000 },
  );
  await page.getByTestId("start-epoch-button").click();
  await expect(page.getByText(/Epoch run .* queued\./)).toBeVisible();
  await expect(page.getByTestId("epoch-runs")).toContainText("completed", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("epoch-runs")).toContainText("2 cond");
}

export async function createCompletedErpRun(page: Page) {
  await expect(page.getByTestId("erp-epoch-run-select")).not.toHaveValue("", {
    timeout: 15_000,
  });
  await page.getByTestId("start-erp-button").click();
  await expect(page.getByText(/ERP run .* queued\./)).toBeVisible();
  await expect(page.getByTestId("erp-runs")).toContainText("completed", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("erp-runs")).toContainText("2 plots");
  await expect(page.getByTestId("erp-preview")).toBeVisible();
}

export async function createComparisonSummary(page: Page) {
  await expect(page.getByTestId("comparison-erp-run-select")).not.toHaveValue("", {
    timeout: 15_000,
  });
  await page.getByTestId("start-comparison-button").click();
  await expect(page.getByText("Comparison summary generated.")).toBeVisible();
  await expect(page.getByTestId("comparison-summary")).toContainText("Difference");
  await expect(page.getByTestId("comparison-summary")).toContainText("deferred");
}
