import { expect, type Page } from "@playwright/test";
import { Buffer } from "node:buffer";
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
): Promise<{ datasetId: string; preprocessingRunId: string }> {
  await page.goto("/");
  await expect(page.getByTestId("setup-workspace")).toBeVisible();

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

  const activeDatasetId = (
    await page.getByTestId("stage-dataset-value").textContent()
  )?.trim();
  expect(activeDatasetId).toBeTruthy();

  await expect(page.getByTestId("setup-workspace")).toBeVisible();
  await expect(page.getByTestId("analysis-workspace")).toHaveCount(0);
  await page.getByTestId(`dataset-row-${activeDatasetId}`).click();
  await expect(page.getByTestId("setup-workspace")).toBeVisible();
  await expect(page.getByTestId("analysis-workspace")).toHaveCount(0);

  await page.getByRole("button", { name: "Continue Analysis" }).click();
  await expect(page.getByTestId("analysis-workspace")).toBeVisible();
  await expect(page.getByTestId("analysis-workspace")).toContainText(
    activeDatasetId ?? "",
  );
  await expect(page.getByText("Ingestion And Preprocessing")).toBeVisible();
  await expect(page.getByText("Supported formats: FIF, EDF, BDF")).toBeVisible();
  await expect(
    page.getByText("tests/fixtures/eeg/sample_resting_raw.fif"),
  ).toBeVisible();
  await expect(page.getByText("Supported formats: CSV or TSV")).toBeVisible();
  await expect(
    page.getByText("tests/fixtures/events/psychopy_minimal.csv"),
  ).toBeVisible();
  await expect(page.getByTestId("eeg-upload-status")).toHaveText(
    "No EEG file selected",
  );
  await expect(page.getByTestId("event-upload-status")).toHaveText(
    "No event log selected",
  );
  await expect(page.getByTestId("upload-eeg-button")).toBeDisabled();
  await expect(page.getByTestId("upload-events-button")).toBeDisabled();

  await page.getByTestId("event-file-input").setInputFiles({
    name: "events.xlsx",
    mimeType:
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    buffer: Buffer.from("not a csv"),
  });
  await expect(page.getByText("Unsupported event log.")).toBeVisible();
  await expect(page.getByTestId("event-upload-status")).toHaveText(
    "No event log selected",
  );

  await page.getByTestId("validate-dataset-button").click();
  await expect(page.getByText("Dataset has blocking errors.")).toBeVisible();
  await expect(page.getByTestId("validation-errors")).toContainText(
    "recording_missing",
  );
  await expect(page.getByTestId("validation-errors")).toContainText(
    "recording_id",
  );
  await expect(page.getByTestId("validation-errors")).toContainText(
    "Next action: Upload a supported EEG recording",
  );
  await expect(page.getByTestId("validation-errors")).toContainText(
    "event_log_missing",
  );
  await expect(page.getByTestId("validation-warnings")).toContainText(
    "No warnings.",
  );

  await page.getByTestId("eeg-file-input").setInputFiles(eegFixture);
  await expect(page.getByTestId("eeg-upload-status")).toContainText(
    path.basename(eegFixture),
  );
  await page.getByTestId("upload-eeg-button").click();
  await expect(page.getByText("EEG file uploaded.")).toBeVisible();
  await expect(page.getByTestId("eeg-upload-status")).toContainText(
    path.basename(eegFixture),
  );

  await page.getByTestId("event-file-input").setInputFiles(eventFixture);
  await expect(page.getByTestId("event-upload-status")).toContainText(
    path.basename(eventFixture),
  );
  await page.getByTestId("upload-events-button").click();
  await expect(page.getByText("Event log uploaded.")).toBeVisible();
  await expect(page.getByTestId("event-upload-status")).toContainText(
    path.basename(eventFixture),
  );

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
  await expect(page.getByTestId("analysis-workspace")).toBeVisible();
  await expect(page.getByTestId("analysis-workspace")).toContainText(
    activeDatasetId ?? "",
  );
  await expect(page.getByTestId("stage-events-value")).toHaveText(
    mappedEventsText ?? "",
  );

  await page.getByTestId("validate-dataset-button").click();
  await expect(page.getByText("Dataset is valid.")).toBeVisible();
  await expect(page.getByTestId("validation-ready-message")).toContainText(
    "Dataset is ready for preprocessing.",
  );
  await expect(page.getByTestId("validation-panel")).toContainText(
    "Preprocessing is available",
  );
  await expect(page.getByTestId("validation-errors")).toContainText(
    "No blocking errors.",
  );

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
  const preprocessingRunsText =
    (await page.getByTestId("preprocessing-runs").textContent()) ?? "";
  const preprocessingRunId = preprocessingRunsText.match(
    /preprocess-[a-z0-9-]+/,
  )?.[0];
  expect(preprocessingRunId).toBeTruthy();

  return {
    datasetId: activeDatasetId ?? "",
    preprocessingRunId: preprocessingRunId ?? "",
  };
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
  await expect(page.getByTestId("epoch-runs")).toContainText("Lineage");
  await expect(page.getByTestId("epoch-runs")).toContainText("Preprocessing");
  await expect(page.getByTestId("epoch-runs")).toContainText("Epoch");
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
  await expect(page.getByTestId("erp-runs")).toContainText("Lineage");
  await expect(page.getByTestId("erp-runs")).toContainText("Preprocessing");
  await expect(page.getByTestId("erp-runs")).toContainText("Epoch");
  await expect(page.getByTestId("erp-runs")).toContainText("ERP");
  await expect(page.getByTestId("erp-preview")).toBeVisible();
}

export async function createComparisonSummary(page: Page) {
  await expect(page.getByTestId("comparison-erp-run-select")).not.toHaveValue("", {
    timeout: 15_000,
  });
  await page.getByTestId("start-comparison-button").click();
  await expect(page.getByText("Comparison summary generated.")).toBeVisible();
  await expect(page.getByTestId("comparison-summary")).toContainText("Difference");
  await expect(page.getByTestId("comparison-summary")).toContainText("unavailable");
  await expect(page.getByTestId("erp-runs")).toContainText("Comparison");
}
