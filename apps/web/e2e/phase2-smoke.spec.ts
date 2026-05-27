import { expect, test } from "@playwright/test";
import { createPreprocessedDataset } from "./helpers/workflow";

const apiBaseUrl = "http://127.0.0.1:8010";

test("uploads, validates, and completes preprocessing from the browser UI", async ({
  page,
}) => {
  const { datasetId, preprocessingRunId } = await createPreprocessedDataset(page, {
    project: "Phase 2 E2E Project",
    experiment: "Oddball E2E",
    participant: "sub-e2e",
    session: "ses-e2e",
  });

  const qcResponse = await page.request.get(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/qc-summary?run_id=${encodeURIComponent(
      preprocessingRunId,
    )}`,
  );
  expect(qcResponse.ok()).toBeTruthy();
  const qcPayload = await qcResponse.json();
  expect(qcPayload.summary.preprocessing.phase_b_artifacts).toEqual(
    expect.objectContaining({
      bad_channel_report: expect.any(Object),
      artifact_rejection_report: expect.any(Object),
      ica_report: expect.any(Object),
      before_after_qc: expect.any(Object),
    }),
  );

  const integrityResponse = await page.request.get(
    `${apiBaseUrl}/runs/${encodeURIComponent(preprocessingRunId)}/artifact-integrity`,
  );
  expect(integrityResponse.ok()).toBeTruthy();
  const integrityPayload = await integrityResponse.json();
  expect(integrityPayload.integrity.status).toBe("ok");
  expect(
    integrityPayload.integrity.artifacts.map(
      (artifact: { logical_name: string }) => artifact.logical_name,
    ),
  ).toEqual(
    expect.arrayContaining([
      "bad_channel_report",
      "artifact_rejection_report",
      "ica_report",
      "before_after_qc",
    ]),
  );

  const exportResponse = await page.request.get(
    `${apiBaseUrl}/datasets/${encodeURIComponent(datasetId)}/export-bundle?run_id=${encodeURIComponent(
      preprocessingRunId,
    )}`,
  );
  expect(exportResponse.ok()).toBeTruthy();
  expect(exportResponse.headers()["content-type"]).toContain("application/zip");

  await page
    .getByTestId(`save-template-preprocessing-${preprocessingRunId}`)
    .click();
  await expect(page.getByText("Workflow template saved.")).toBeVisible();
  await expect(page.getByTestId("workflow-template-panel")).toContainText(
    "Excluded Subject-Specific Fields",
  );
  await expect(page.getByTestId("workflow-template-panel")).toContainText(
    "Review-Needed Fields",
  );
  await expect(page.getByTestId("workflow-template-select")).not.toHaveValue("");

  await page.getByTestId("resample-hz-input").fill("60");
  await expect(page.getByTestId("resample-hz-input")).toHaveValue("60");
  await page.getByTestId("apply-workflow-template-button").click();
  await expect(
    page.getByText("Workflow template applied to the current dataset config."),
  ).toBeVisible();
  await expect(page.getByTestId("resample-hz-input")).toHaveValue("50");

  await page.getByTestId("start-batch-button").click();
  await expect(page.getByText(/Batch .* queued for 1 dataset/)).toBeVisible();
  await expect(page.getByTestId("batch-run-table")).toContainText(datasetId);
  await expect(page.getByTestId("batch-run-table")).toContainText("completed", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("batch-run-table")).toContainText("preprocess-");
});
