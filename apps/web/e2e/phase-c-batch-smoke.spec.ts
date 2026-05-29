import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPreprocessedDataset } from "./helpers/workflow";

const apiBaseUrl = "http://127.0.0.1:8010";
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

test("runs a multi-dataset batch and retries one failed subject", async ({
  page,
}) => {
  const { datasetId, preprocessingRunId } = await createPreprocessedDataset(page, {
    project: "Phase C Batch E2E Project",
    experiment: "Batch Retry E2E",
    participant: "sub-batch-a",
    session: "ses-batch-a",
  });

  await page
    .getByTestId(`save-template-preprocessing-${preprocessingRunId}`)
    .click();
  await expect(page.getByText("Workflow template saved.")).toBeVisible();
  await expect(page.getByTestId("workflow-template-select")).not.toHaveValue("");

  const failedDataset = await createValidDatasetViaApi(page, {
    participant: "sub-batch-b",
    session: "ses-batch-b",
  });
  fs.writeFileSync(failedDataset.eegStoredPath, "corrupt fif for retry smoke");

  await page.reload();
  await expect(page.getByTestId("analysis-workspace")).toBeVisible();
  await expect(page.getByTestId("workflow-template-select")).not.toHaveValue("");
  await expect(page.getByText("2 dataset(s)")).toBeVisible();

  await page.getByTestId("apply-workflow-template-button").click();
  await expect(
    page.getByText("Workflow template applied to the current dataset config."),
  ).toBeVisible();

  await page.getByTestId("start-batch-button").click();
  await expect(page.getByText(/Batch .* queued for 2 dataset/)).toBeVisible();
  const batchId = await selectedBatchId(page);
  expect(batchId).toBeTruthy();

  const batchTable = page.getByTestId("batch-run-table");
  await expect(batchTable).toContainText(datasetId);
  await expect(batchTable).toContainText(failedDataset.datasetId);
  await expect(batchTable).toContainText("failed", { timeout: 90_000 });
  await expect(batchTable).toContainText("completed");

  let batch = await getBatch(page, batchId);
  const failedItem = batch.items.find(
    (item: BatchItem) => item.dataset_id === failedDataset.datasetId,
  );
  expect(failedItem?.status).toBe("failed");
  expect(failedItem?.run_ids.preprocessing).toMatch(/^preprocess-/);

  await uploadValidEeg(page, failedDataset.datasetId);
  await page.getByTestId(`retry-batch-item-${failedItem?.item_id}`).click();
  await expect(page.getByText(`Retry queued for ${failedItem?.item_id}.`)).toBeVisible();
  await expect(batchTable).toContainText("Attempt 2", { timeout: 90_000 });
  await expect(batchTable).toContainText("Previous run:");

  batch = await waitForBatchStatus(page, batchId, "completed");
  expect(batch.items.map((item: BatchItem) => item.status)).toEqual([
    "completed",
    "completed",
  ]);
  const retriedItem = batch.items.find(
    (item: BatchItem) => item.dataset_id === failedDataset.datasetId,
  );
  expect(retriedItem?.attempt).toBe(2);
  expect(retriedItem?.previous_run_ids.preprocessing).toBe(
    failedItem?.run_ids.preprocessing,
  );
  expect(retriedItem?.run_ids.preprocessing).toMatch(/^preprocess-/);
  expect(retriedItem?.run_ids.preprocessing).not.toBe(
    failedItem?.run_ids.preprocessing,
  );

  const summaryResponse = await page.request.get(
    `${apiBaseUrl}/batches/${encodeURIComponent(batchId)}/summary-artifact`,
  );
  expect(summaryResponse.ok()).toBeTruthy();
  const summary = await summaryResponse.json();
  expect(summary.item_counts.completed).toBe(2);
  expect(
    summary.items.map((item: { artifact_manifests: Record<string, unknown> }) =>
      Boolean(item.artifact_manifests.preprocessing),
    ),
  ).toEqual([true, true]);
});

type BatchItem = {
  dataset_id: string;
  item_id: string;
  status: string;
  attempt: number;
  run_ids: Record<string, string>;
  previous_run_ids: Record<string, string>;
};

async function createValidDatasetViaApi(
  page: Page,
  labels: { participant: string; session: string },
): Promise<{ datasetId: string; eegStoredPath: string }> {
  const datasetsResponse = await page.request.get(`${apiBaseUrl}/datasets`);
  expect(datasetsResponse.ok()).toBeTruthy();
  const datasetsPayload = await datasetsResponse.json();
  const sourceDataset = datasetsPayload.datasets[0];
  const createResponse = await page.request.post(`${apiBaseUrl}/datasets`, {
    data: {
      project_id: sourceDataset.project_id,
      experiment_id: sourceDataset.experiment_id,
      participant_label: labels.participant,
      session_label: labels.session,
    },
  });
  expect(createResponse.ok()).toBeTruthy();
  const created = await createResponse.json();
  const datasetId = created.dataset_id;

  const eegUpload = await uploadValidEeg(page, datasetId);
  await uploadEvents(page, datasetId);
  const mappingResponse = await page.request.post(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/events/mapping`,
    {
      data: {
        mapping: {
          onset_seconds: "onset",
          trial_type: "trial_type",
        },
      },
    },
  );
  expect(mappingResponse.ok()).toBeTruthy();

  const validationResponse = await page.request.get(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/validation`,
  );
  expect(validationResponse.ok()).toBeTruthy();
  const validation = await validationResponse.json();
  expect(validation.valid).toBeTruthy();

  return {
    datasetId,
    eegStoredPath: eegUpload.uploaded_file.stored_path,
  };
}

async function uploadValidEeg(
  page: Page,
  datasetId: string,
) {
  const response = await page.request.post(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/files/eeg`,
    {
      multipart: {
        file: {
          name: "sample_resting_raw.fif",
          mimeType: "application/octet-stream",
          buffer: fs.readFileSync(eegFixture),
        },
      },
    },
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function uploadEvents(
  page: Page,
  datasetId: string,
) {
  const response = await page.request.post(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/files/events`,
    {
      multipart: {
        file: {
          name: "psychopy_minimal.csv",
          mimeType: "text/csv",
          buffer: fs.readFileSync(eventFixture),
        },
      },
    },
  );
  expect(response.ok()).toBeTruthy();
}

async function selectedBatchId(page: Page) {
  return page.getByTestId("batch-select").inputValue();
}

async function getBatch(page: Page, batchId: string) {
  const response = await page.request.get(
    `${apiBaseUrl}/batches/${encodeURIComponent(batchId)}`,
  );
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function waitForBatchStatus(
  page: Page,
  batchId: string,
  status: string,
) {
  const started = Date.now();
  while (Date.now() - started < 90_000) {
    const batch = await getBatch(page, batchId);
    if (batch.status === status) {
      return batch;
    }
    await page.waitForTimeout(1000);
  }
  throw new Error(`Batch ${batchId} did not reach ${status}`);
}
