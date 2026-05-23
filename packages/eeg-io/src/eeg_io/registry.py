from dataclasses import asdict
from pathlib import Path
from typing import Any
import json

from eeg_core.domain import (
    Dataset,
    DatasetStatus,
    EventColumnMapping,
    Experiment,
    Participant,
    Project,
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
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
