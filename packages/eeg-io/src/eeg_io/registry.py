from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import os
import tempfile

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    EventLog,
    Experiment,
    NormalizedEvent,
    Participant,
    PreprocessingConfig,
    PreprocessingRun,
    PreprocessingRunStatus,
    Project,
    Recording,
    UploadedFile,
    UploadedFileKind,
    recording_metadata_from_dict,
)


JsonObject = dict[str, Any]


class JsonRegistryError(Exception):
    pass


class JsonRegistryRepository:
    def __init__(self, uploads_root: Path):
        self.uploads_root = uploads_root

    @property
    def projects_path(self) -> Path:
        return self.uploads_root / "projects.json"

    @property
    def experiments_path(self) -> Path:
        return self.uploads_root / "experiments.json"

    @property
    def participants_path(self) -> Path:
        return self.uploads_root / "participants.json"

    @property
    def datasets_root(self) -> Path:
        return self.uploads_root / "datasets"

    def initialize(self) -> None:
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        self.datasets_root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.projects_path,
            self.experiments_path,
            self.participants_path,
        ):
            if not path.exists():
                _write_json(path, [])

    def save_project(self, project: Project) -> Project:
        self.initialize()
        projects = _upsert_by_id(
            _read_json_list(self.projects_path),
            asdict(project),
            "project_id",
        )
        _write_json(self.projects_path, projects)
        return project

    def list_projects(self) -> list[Project]:
        self.initialize()
        return [_project_from_json(item) for item in _read_json_list(self.projects_path)]

    def get_project(self, project_id: str) -> Project | None:
        return _find_by_id(self.list_projects(), "project_id", project_id)

    def save_experiment(self, experiment: Experiment) -> Experiment:
        self.initialize()
        experiments = _upsert_by_id(
            _read_json_list(self.experiments_path),
            asdict(experiment),
            "experiment_id",
        )
        _write_json(self.experiments_path, experiments)
        return experiment

    def list_experiments(self, project_id: str | None = None) -> list[Experiment]:
        self.initialize()
        experiments = [
            _experiment_from_json(item)
            for item in _read_json_list(self.experiments_path)
        ]
        if project_id is None:
            return experiments
        return [
            experiment
            for experiment in experiments
            if experiment.project_id == project_id
        ]

    def get_experiment(self, experiment_id: str) -> Experiment | None:
        return _find_by_id(self.list_experiments(), "experiment_id", experiment_id)

    def save_participant(self, participant: Participant) -> Participant:
        self.initialize()
        participants = _upsert_by_id(
            _read_json_list(self.participants_path),
            asdict(participant),
            "participant_id",
        )
        _write_json(self.participants_path, participants)
        return participant

    def list_participants(self, project_id: str | None = None) -> list[Participant]:
        self.initialize()
        participants = [
            _participant_from_json(item)
            for item in _read_json_list(self.participants_path)
        ]
        if project_id is None:
            return participants
        return [
            participant
            for participant in participants
            if participant.project_id == project_id
        ]

    def get_participant(self, participant_id: str) -> Participant | None:
        return _find_by_id(self.list_participants(), "participant_id", participant_id)

    def save_dataset(self, dataset: Dataset) -> Dataset:
        self.initialize()
        dataset_directory = self.dataset_directory(dataset.dataset_id)
        dataset_directory.mkdir(parents=True, exist_ok=True)
        self.eeg_directory(dataset.dataset_id).mkdir(parents=True, exist_ok=True)
        self.events_directory(dataset.dataset_id).mkdir(parents=True, exist_ok=True)
        _write_json(self.dataset_metadata_path(dataset.dataset_id), asdict(dataset))
        return dataset

    def update_dataset(self, dataset: Dataset) -> Dataset:
        if not self.dataset_metadata_path(dataset.dataset_id).exists():
            raise JsonRegistryError(f"Dataset not found: {dataset.dataset_id}")
        return self.save_dataset(dataset)

    def list_datasets(self, project_id: str | None = None) -> list[Dataset]:
        self.initialize()
        datasets = [
            _dataset_from_json(_read_json_object(path))
            for path in sorted(self.datasets_root.glob("*/metadata.json"))
        ]
        if project_id is None:
            return datasets
        return [dataset for dataset in datasets if dataset.project_id == project_id]

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        path = self.dataset_metadata_path(dataset_id)
        if not path.exists():
            return None
        return _dataset_from_json(_read_json_object(path))

    def dataset_directory(self, dataset_id: str) -> Path:
        return self.datasets_root / dataset_id

    def eeg_directory(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "eeg"

    def events_directory(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "events"

    def dataset_metadata_path(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "metadata.json"

    def save_uploaded_file(self, uploaded_file: UploadedFile) -> UploadedFile:
        self.save_dataset_files_directory(uploaded_file.dataset_id)
        files = _upsert_by_id(
            self.list_uploaded_files(uploaded_file.dataset_id, initialize=False),
            asdict(uploaded_file),
            "file_id",
        )
        _write_json(self.uploaded_files_path(uploaded_file.dataset_id), files)
        return uploaded_file

    def list_uploaded_files(
        self,
        dataset_id: str,
        initialize: bool = True,
    ) -> list[UploadedFile] | list[JsonObject]:
        path = self.uploaded_files_path(dataset_id)
        if not path.exists():
            if initialize:
                self.save_dataset_files_directory(dataset_id)
                _write_json(path, [])
            return []

        files = _read_json_list(path)
        if not initialize:
            return files
        return [_uploaded_file_from_json(item) for item in files]

    def save_recording(self, recording: Recording) -> Recording:
        self.save_dataset_files_directory(recording.dataset_id)
        _write_json(self.recording_path(recording.dataset_id), asdict(recording))
        return recording

    def get_recording(self, dataset_id: str) -> Recording | None:
        path = self.recording_path(dataset_id)
        if not path.exists():
            return None
        return _recording_from_json(_read_json_object(path))

    def save_events_preview(self, dataset_id: str, preview: JsonObject) -> JsonObject:
        self.save_dataset_files_directory(dataset_id)
        _write_json(self.events_preview_path(dataset_id), preview)
        return preview

    def get_events_preview(self, dataset_id: str) -> JsonObject | None:
        path = self.events_preview_path(dataset_id)
        if not path.exists():
            return None
        return _read_json_object(path)

    def save_event_log(self, event_log: EventLog) -> EventLog:
        self.save_dataset_files_directory(event_log.dataset_id)
        _write_json(self.event_log_path(event_log.dataset_id), asdict(event_log))
        return event_log

    def get_event_log(self, dataset_id: str) -> EventLog | None:
        path = self.event_log_path(dataset_id)
        if not path.exists():
            return None
        return _event_log_from_json(_read_json_object(path))

    def save_dataset_files_directory(self, dataset_id: str) -> None:
        self.dataset_directory(dataset_id).mkdir(parents=True, exist_ok=True)
        self.eeg_directory(dataset_id).mkdir(parents=True, exist_ok=True)
        self.events_directory(dataset_id).mkdir(parents=True, exist_ok=True)

    def uploaded_files_path(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "uploaded_files.json"

    def recording_path(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "recording.json"

    def events_preview_path(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "events_preview.json"

    def event_log_path(self, dataset_id: str) -> Path:
        return self.dataset_directory(dataset_id) / "event_log.json"


class JsonRunRepository:
    def __init__(self, runs_root: Path):
        self.runs_root = runs_root

    def initialize(self) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)

    def save_preprocessing_run(self, run: PreprocessingRun) -> PreprocessingRun:
        self.initialize()
        _write_json(self.preprocessing_run_path(run.run_id), asdict(run))
        return run

    def get_preprocessing_run(self, run_id: str) -> PreprocessingRun | None:
        path = self.preprocessing_run_path(run_id)
        if not path.exists():
            return None
        return _preprocessing_run_from_json(_read_json_object(path))

    def list_preprocessing_runs(
        self,
        dataset_id: str | None = None,
    ) -> list[PreprocessingRun]:
        self.initialize()
        runs = [
            _preprocessing_run_from_json(_read_json_object(path))
            for path in sorted(self.runs_root.glob("*/run.json"))
        ]
        if dataset_id is None:
            return runs
        return [run for run in runs if run.dataset_id == dataset_id]

    def preprocessing_run_directory(self, run_id: str) -> Path:
        return self.runs_root / run_id

    def preprocessing_run_path(self, run_id: str) -> Path:
        return self.preprocessing_run_directory(run_id) / "run.json"


def _project_from_json(data: JsonObject) -> Project:
    return Project(
        project_id=str(data["project_id"]),
        name=str(data["name"]),
        description=data.get("description"),
        metadata=dict(data.get("metadata", {})),
    )


def _experiment_from_json(data: JsonObject) -> Experiment:
    return Experiment(
        experiment_id=str(data["experiment_id"]),
        project_id=str(data["project_id"]),
        name=str(data["name"]),
        task_name=data.get("task_name"),
        default_event_mapping=EventColumnMapping(
            **data.get("default_event_mapping", {})
        ),
        metadata=dict(data.get("metadata", {})),
    )


def _participant_from_json(data: JsonObject) -> Participant:
    return Participant(
        participant_id=str(data["participant_id"]),
        project_id=str(data["project_id"]),
        label=str(data["label"]),
        group=data.get("group"),
        metadata=dict(data.get("metadata", {})),
    )


def _dataset_from_json(data: JsonObject) -> Dataset:
    return Dataset(
        dataset_id=str(data["dataset_id"]),
        project_id=str(data["project_id"]),
        experiment_id=str(data["experiment_id"]),
        participant_id=str(data["participant_id"]),
        session_id=str(data["session_id"]),
        status=DatasetStatus(data.get("status", DatasetStatus.DRAFT)),
        recording_id=data.get("recording_id"),
        event_log_id=data.get("event_log_id"),
        metadata=dict(data.get("metadata", {})),
    )


def _uploaded_file_from_json(data: JsonObject) -> UploadedFile:
    return UploadedFile(
        file_id=str(data["file_id"]),
        dataset_id=str(data["dataset_id"]),
        kind=UploadedFileKind(data["kind"]),
        original_filename=str(data["original_filename"]),
        stored_path=str(data["stored_path"]),
        content_type=data.get("content_type"),
        size_bytes=data.get("size_bytes"),
        checksum_sha256=data.get("checksum_sha256"),
    )


def _recording_from_json(data: JsonObject) -> Recording:
    return Recording(
        recording_id=str(data["recording_id"]),
        dataset_id=str(data["dataset_id"]),
        file_id=str(data["file_id"]),
        metadata=recording_metadata_from_dict(data["metadata"]),
    )


def _event_log_from_json(data: JsonObject) -> EventLog:
    return EventLog(
        event_log_id=str(data["event_log_id"]),
        dataset_id=str(data["dataset_id"]),
        file_id=str(data["file_id"]),
        mapping=EventColumnMapping(**data.get("mapping", {})),
        row_count=int(data["row_count"]),
        events=[
            _normalized_event_from_json(event)
            for event in data.get("events", [])
        ],
    )


def _preprocessing_config_from_json(data: JsonObject) -> PreprocessingConfig:
    return PreprocessingConfig(
        high_pass_hz=_optional_float(data.get("high_pass_hz")),
        low_pass_hz=_optional_float(data.get("low_pass_hz")),
        notch_hz=_optional_float(data.get("notch_hz")),
        resample_hz=_optional_float(data.get("resample_hz")),
        reference=data.get("reference"),
    )


def _preprocessing_run_from_json(data: JsonObject) -> PreprocessingRun:
    return PreprocessingRun(
        run_id=str(data["run_id"]),
        dataset_id=str(data["dataset_id"]),
        config=_preprocessing_config_from_json(data.get("config", {})),
        status=PreprocessingRunStatus(
            data.get("status", PreprocessingRunStatus.PENDING)
        ),
        started_at_utc=data.get("started_at_utc"),
        finished_at_utc=data.get("finished_at_utc"),
        cancel_requested_at_utc=data.get("cancel_requested_at_utc"),
        output_path=data.get("output_path"),
        output_metadata=dict(data.get("output_metadata", {})),
        warnings=[str(warning) for warning in data.get("warnings", [])],
        errors=[str(error) for error in data.get("errors", [])],
    )


def _normalized_event_from_json(data: JsonObject) -> NormalizedEvent:
    return NormalizedEvent(
        onset_seconds=float(data["onset_seconds"]),
        source_row=int(data["source_row"]),
        duration_seconds=_optional_float(data.get("duration_seconds")),
        trial_type=data.get("trial_type"),
        stimulus=data.get("stimulus"),
        response=data.get("response"),
        correct=data.get("correct"),
        reaction_time_seconds=_optional_float(data.get("reaction_time_seconds")),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _find_by_id(items: list[Any], field_name: str, expected_id: str) -> Any | None:
    for item in items:
        if getattr(item, field_name) == expected_id:
            return item
    return None


def _upsert_by_id(
    items: list[JsonObject],
    item: JsonObject,
    id_field: str,
) -> list[JsonObject]:
    next_items = [
        existing
        for existing in items
        if existing.get(id_field) != item[id_field]
    ]
    next_items.append(item)
    return sorted(next_items, key=lambda existing: str(existing[id_field]))


def _read_json_list(path: Path) -> list[JsonObject]:
    data = _read_json(path)
    if not isinstance(data, list):
        raise JsonRegistryError(f"Expected JSON list in {path}")
    return data


def _read_json_object(path: Path) -> JsonObject:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise JsonRegistryError(f"Expected JSON object in {path}")
    return data


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JsonRegistryError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=path.parent,
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
