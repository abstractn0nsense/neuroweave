# Architecture

This repository starts with an EEG workflow-first layout. Chat can become an interface later, but the durable center of the system should be EEG data, processing steps, workflow execution, and results.

## Folders

### `apps/`

Runnable applications live here.

- `apps/web`: browser UI for uploading EEG data, configuring workflows, reviewing processing state, and inspecting results.
- `apps/api`: HTTP or RPC entrypoint for workflow jobs, datasets, processing runs, and future chat commands.

Applications can depend on packages, but packages should not depend on applications.

### `packages/eeg-core/`

Framework-independent EEG domain logic lives here.

Use this package for:

- recording, channel, montage, event, annotation, and dataset models
- pipeline contracts and domain-level validation rules
- ports/interfaces for loading data, storing results, and running analysis
- shared vocabulary for EEG workflow packages

Avoid importing SDKs, database clients, UI frameworks, plotting libraries, or server frameworks from this package.

### `packages/eeg-processing/`

Signal processing and analysis steps live here.

Use this package for:

- filtering and resampling
- artifact detection and correction
- epoching and feature extraction
- analysis modules that operate on EEG domain objects

Processing code should depend on `eeg-core` contracts and keep storage/UI concerns outside this package.

### `packages/eeg-io/`

EEG file and dataset adapters live here.

Use this package for:

- EDF, BDF, FIF, CSV, and other file readers or writers
- dataset import/export helpers
- metadata normalization at system boundaries

I/O code should convert external formats into `eeg-core` models.

### `packages/workflow-engine/`

Pipeline orchestration lives here.

Use this package for:

- workflow definitions
- step dependency graphs
- job state and execution results
- retry, cancellation, and progress contracts

The workflow engine composes EEG I/O and processing packages, but it should not know about UI components.

### `packages/chat-interface/`

Future conversational workflow control lives here.

Use this package later for:

- translating chat commands into workflow actions
- summarizing workflow state for a chat UI
- connecting an LLM or assistant runtime to workflow APIs

Do not put EEG domain rules here. Chat should remain an interface over the workflow system.

### `packages/shared/`

Small cross-cutting code lives here.

Use this package for generic config, shared types, constants, and tiny utilities. Keep EEG-specific behavior in `eeg-core`.

### `tests/`

Repository-level test fixtures and integration test support live here. Package-specific tests can live near the code once a test framework is chosen.

## Compatibility Rules

1. Keep EEG domain logic in `eeg-core`.
2. Keep signal processing in `eeg-processing`.
3. Put external file and dataset formats in `eeg-io`.
4. Let `workflow-engine` compose processing steps without owning the EEG domain.
5. Keep `chat-interface` as an optional control layer over workflows.
6. Let `apps` compose packages instead of putting business logic directly in app entrypoints.
7. Introduce framework-specific folders only inside the app or adapter that uses that framework.
8. Prefer stable interfaces between folders before adding implementation details.
