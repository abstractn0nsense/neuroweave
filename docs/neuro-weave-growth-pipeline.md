# NeuroWeave Growth Pipeline

This pipeline translates the KAIST OverEdge idea document into a concrete product,
engineering, AI, and commercialization path. The goal is not to become another EEG
plotting tool. The goal is to become a reproducible neuroscience research workspace
that starts with EEG preprocessing and ERP workflows, then expands into AI-assisted
workflow orchestration and collaboration.

## Current Position

NeuroWeave is currently usable as a local research workflow prototype:

- project, experiment, dataset, EEG file, and event-log intake
- split Setup and Analysis workspace modes so study organization is separated
  from execution
- metadata and event validation
- MNE-based preprocessing
- epoch generation
- ERP artifact generation and preview
- descriptive ERP condition comparison preparation
- local run provenance, diagnostics, and export bundles

The next development should move from "it runs" to "researchers can trust, compare,
repeat, and share the workflow."

## North Star

NeuroWeave should become the workspace where a neuroscience researcher can:

1. import raw EEG and event data;
2. understand whether the dataset is valid;
3. run a reproducible preprocessing and analysis workflow;
4. inspect every artifact, warning, parameter, and decision;
5. compare conditions and export publishable analysis bundles;
6. collaborate with lab members around the same workflow history;
7. use AI assistance for validation, debugging, workflow recommendation, and
   research-context summarization.

## Development Principles

- Trust before automation: AI suggestions must be grounded in recorded workflow
  state, parameters, warnings, and artifacts.
- Reproducibility before breadth: add fewer analyses, but make each one repeatable.
- Explicit transitions before hidden automation: selecting a dataset should not
  silently launch or advance analysis. Users should confirm when moving from setup
  into execution.
- Workflow first, chat second: chat should operate the workflow, not replace it.
- Local-first before SaaS: prove the research loop locally, then add accounts and
  collaboration.
- Benchling-like expansion: start with one painful workflow, then become the system
  of record for neuroscience research operations.

## Pipeline

### Stage 1: Research-Grade EEG MVP Hardening

Goal: turn the current prototype into a dependable local tool for EEG/ERP studies.

Build:

- stable run schema for preprocessing, epoch, ERP, comparison, and export
- artifact manifests for every completed run
- versioned config snapshots and immutable completed-run records
- clear dataset readiness gates
- documented Setup-to-Analysis handoff with user-visible active dataset context
- robust local app launcher and recovery from interrupted runs
- sample workflow gallery using public EEG datasets

Acceptance criteria:

- public EDF/FIF/BDF examples complete end-to-end without manual code edits
- every completed run can be re-opened with matching files and metadata
- every failed run remains queryable with actionable errors and warnings
- one-click local launch works for non-developer users
- user-facing Korean and English guides remain aligned with the current UI

Suggested product milestone: "NeuroWeave Local Research Preview."

### Stage 2: Analysis Depth And Scientific Credibility

Goal: move beyond descriptive ERP preview into workflows that researchers can use in
pilot analyses.

Build:

- ICA and bad-channel workflow with before/after diagnostics
- baseline correction controls and explicit reporting
- automated artifact detection summaries
- condition-level ERP statistics:
  - mean amplitude tests
  - peak latency/amplitude summaries
  - confidence intervals or bootstrap summaries where appropriate
- time-frequency analysis MVP
- topographic map visualization
- PDF/HTML analysis report generation
- BIDS import/export compatibility checks

Acceptance criteria:

- output reports include methods-style parameter summaries
- comparison outputs clearly separate descriptive metrics from inference
- generated bundles contain raw input identity, preprocessing config, analysis
  config, software versions, plots, tables, and warnings
- pilot users can reproduce a result from an exported bundle

Suggested product milestone: "Reproducible EEG Analysis Workbench."

### Stage 3: Workflow Engine And Template System

Goal: stop treating runs as isolated actions and make full pipelines reusable.

Build:

- workflow templates:
  - resting-state preprocessing
  - ERP oddball
  - motor imagery
  - generic event-related EEG
- pipeline graph model with step dependencies
- run comparison across parameter versions
- retry/cancel/resume at step level
- batch execution for multiple subjects or sessions
- template-level validation and expected artifact contracts

Acceptance criteria:

- users can apply the same workflow to multiple participants
- parameter changes create new versioned workflow runs, not overwritten state
- workflow history makes it clear why two results differ
- batch failures isolate one participant without corrupting the whole batch

Suggested product milestone: "Workflow Templates And Batch Processing."

### Stage 4: AI-Assisted Research Workflow

Goal: add AI where NeuroWeave has structured context that general chat tools do not.

Build:

- workflow health summary:
  - missing metadata
  - suspicious event timing
  - preprocessing warnings
  - failed artifacts
- AI explanation of run warnings and suggested next checks
- preprocessing recommendation assistant based on dataset metadata and selected
  workflow template
- AI-generated methods draft from provenance and artifact manifests
- natural-language workflow command layer:
  - "run the default ERP workflow"
  - "explain why this epoch run dropped trials"
  - "compare T1 and T2 from 100 to 800 ms"
- guardrails:
  - no silent parameter changes
  - every AI action produces a visible proposed workflow change
  - user approval before executing or modifying analysis state

Acceptance criteria:

- AI answers cite concrete run IDs, files, parameters, and warning records
- AI cannot invent unavailable artifacts or unsupported statistics
- accepted AI recommendations are stored in workflow history
- users can distinguish explanation, recommendation, and execution actions

Suggested product milestone: "AI Research Assistant Beta."

### Stage 5: Collaboration And Lab Workspace

Goal: make NeuroWeave useful for small labs, not only individual local analysis.

Build:

- project spaces with roles:
  - owner
  - analyst
  - reviewer
  - viewer
- comments on datasets, runs, artifacts, and plots
- workflow version history and change notes
- shared template library per lab
- review/approval state for analysis runs
- cloud or shared-server storage adapter
- audit log for analysis decisions

Acceptance criteria:

- one researcher can create a workflow and another can reproduce it
- reviewers can inspect parameters, plots, warnings, and export bundles without
  running local scripts
- analysis changes are attributable to a person or AI-assisted action
- sensitive raw data handling is explicit and configurable

Suggested product milestone: "Collaborative Neuroscience Workspace."

### Stage 6: SaaS And Commercialization

Goal: convert validated research workflows into a product that labs can adopt.

Build:

- hosted workspace deployment
- organization billing and project quotas
- storage policy controls for raw EEG and derived artifacts
- onboarding flow with public datasets and templates
- documentation for lab admins and researchers
- customer feedback loop inside the product
- institution-friendly export and data deletion controls

Initial target users:

- neuroscience and psychology labs running EEG/ERP studies
- BCI research groups
- clinical research teams with EEG data but limited software engineering support
- early-stage neurotechnology teams needing reproducible internal workflows

Pilot strategy:

1. recruit 3 to 5 labs or research teams;
2. run one real dataset per team through NeuroWeave;
3. measure time saved in preprocessing, event validation, and report generation;
4. collect failure cases and missing workflow features;
5. convert the strongest pilot into a case study.

Commercial acceptance criteria:

- non-developer researchers can complete the core workflow after onboarding
- labs see measurable reduction in manual preprocessing/debugging time
- exported reports are useful for internal review or methods drafting
- at least one lab wants shared workspace features enough to pay or commit to a
  longer pilot

## Recommended Next 90 Days

### Weeks 1-2: Reliability Sweep

- fix UI/runtime edge cases found by real public datasets
- add public-data regression workflow for PhysioNet EEGMMI
- harden artifact serving and export-bundle checks
- document known limitations clearly in the app and README

### Weeks 3-5: Research Report MVP

- generate a human-readable analysis report from a completed ERP run
- include dataset metadata, event summary, preprocessing config, epoch config, ERP
  config, plots, comparison summary, warnings, and software versions
- export report plus artifacts as ZIP

### Weeks 6-8: Batch And Template Foundation

- define reusable workflow template JSON
- support applying one template to multiple datasets
- add batch status view
- keep failure isolation per dataset

### Weeks 9-12: AI Assistant Prototype

- implement read-only workflow summarization first
- let AI explain warnings and propose next actions
- require explicit approval for any execution
- store accepted AI recommendations as workflow events

## Key Metrics

Product metrics:

- time from raw EEG upload to first ERP preview
- number of manual files/scripts needed outside NeuroWeave
- successful end-to-end workflows per dataset
- failed runs with actionable diagnostics
- repeatability of results from exported bundles

Research credibility metrics:

- public datasets validated end-to-end
- number of workflow templates with documented assumptions
- number of generated reports accepted by pilot users as useful
- number of reproduced runs from saved provenance

Business metrics:

- pilot labs onboarded
- active datasets per lab
- workflows completed per lab
- conversion from local preview to hosted/shared workspace interest
- willingness to pay for collaboration, batch processing, and reporting

## Immediate Priority

The next highest-leverage milestone is not a chat layer. It is a polished,
research-grade local MVP with public dataset demos, robust reports, export bundles,
and repeatable workflow templates. Once NeuroWeave has reliable structured workflow
state, AI assistance becomes defensible and differentiated.
