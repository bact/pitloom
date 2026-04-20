# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom SDK for capturing BOM fragments during external script/notebook execution."""

import contextlib
import inspect
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _get_caller_info() -> str:
    """Find the first caller frame outside of the pitloom.loom module."""
    try:
        for frame_info in inspect.stack():
            if frame_info.filename != __file__:
                p = Path(frame_info.filename).absolute()
                try:
                    filename = str(p.relative_to(Path.cwd()))
                except ValueError:
                    filename = p.name

                func_name = frame_info.function
                if func_name == "<module>":
                    return (
                        f"Source: {filename} | "
                        f"Method: inspect_caller (tool: pitloom.loom, "
                        f"function: <module>)"
                    )
                return (
                    f"Source: {filename} | "
                    f"Method: inspect_caller (tool: pitloom.loom, "
                    f"function: {func_name})"
                )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"


class _ActiveShot:
    """Internal state for an active BOM recording shot."""

    def __init__(self, output_file: str, pretty: bool = False):
        self.output_file = output_file
        self.pretty = pretty
        self.doc_uuid = str(uuid4())

        self.creation_info = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        # Create a default Agent to satisfy the createdBy constraint
        person = spdx3.Person(
            spdxId=generate_spdx_id("Person", "pitloom-sdk", self.doc_uuid),
            name="Pitloom SDK (Automated Run)",
            creationInfo=self.creation_info,
        )
        self.creation_info.createdBy = [person.spdxId]

        self.exporter = Spdx3JsonExporter()
        self.exporter.add_person(person)

        self.model: spdx3.ai_AIPackage | None = None
        self.datasets: list[spdx3.dataset_DatasetPackage] = []
        self.validation_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.input_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.output_datasets: list[spdx3.dataset_DatasetPackage] = []

    def set_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
    ) -> None:
        """Define the primary AI model being trained.

        Args:
            name: Model name or file path.
            model_type: Type of model, e.g. ``"supervised"``, ``"text-classification"``.
            hyperparameters: Key-value pairs of hyperparameters known at declaration time.
                Use :meth:`set_model_hyperparameters` to update after training completes.
        """
        caller_info = _get_caller_info()
        self.model = spdx3.ai_AIPackage(
            spdxId=generate_spdx_id("AIPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )
        if model_type is not None:
            self.model.ai_typeOfModel = [model_type]
        if hyperparameters is not None:
            self.model.ai_hyperparameter = [
                spdx3.DictionaryEntry(key=k, value=v)
                for k, v in hyperparameters.items()
            ]
        self.exporter.add_package(self.model)

    def set_model_hyperparameters(self, hyperparameters: dict[str, str]) -> None:
        """Update the active model with hyperparameters captured after training.

        Args:
            hyperparameters: Key-value pairs of hyperparameters (values as strings).
        """
        if self.model is None:
            raise RuntimeError(
                "No model set. Call set_model() before set_model_hyperparameters()."
            )
        self.model.ai_hyperparameter = [
            spdx3.DictionaryEntry(key=k, value=v)
            for k, v in hyperparameters.items()
        ]

    def add_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for training in the current shot.

        Creates a ``trainedOn`` relationship from the model to this dataset.
        For the validation set use :meth:`add_validation_dataset`.
        For raw input datasets in a preprocessing step use :meth:`add_input_dataset`.
        """
        caller_info = _get_caller_info()
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )

        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]

        self.datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_validation_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for validation/testing.

        Creates a ``testedOn`` relationship from the model to this dataset.

        Args:
            name: Dataset name or file path.
            dataset_type: SPDX 3 dataset type string, e.g. ``"text"``, ``"image"``.
        """
        caller_info = _get_caller_info()
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )
        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]

        self.validation_datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_input_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Declare a raw/source dataset consumed by a preprocessing step.

        Use together with :meth:`add_output_dataset` to record dataset lineage.
        Creates ``hasInput`` relationships from each output dataset to this dataset.

        Args:
            name: Dataset name or file path.
            dataset_type: SPDX 3 dataset type string, e.g. ``"text"``, ``"image"``.
        """
        caller_info = _get_caller_info()
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )
        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]

        self.input_datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_output_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        data_preprocessing: list[str] | None = None,
    ) -> None:
        """Declare a derived/processed dataset produced by a preprocessing step.

        Use together with :meth:`add_input_dataset` to record dataset lineage.
        Creates ``hasInput`` relationships from this dataset to all declared input datasets.

        Args:
            name: Dataset name or file path.
            dataset_type: SPDX 3 dataset type string, e.g. ``"text"``, ``"image"``.
            data_preprocessing: List of preprocessing steps applied, e.g.
                ``["thai-text-normalization", "newmm-word-tokenization"]``.
        """
        caller_info = _get_caller_info()
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )
        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]
        if data_preprocessing is not None:
            dataset_pkg.dataset_dataPreprocessing = data_preprocessing

        self.output_datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def finalize(self) -> None:
        """Finalize the shot and output the SBOM fragment."""
        # model trainedOn training datasets
        if self.model and self.datasets:
            for dataset in self.datasets:
                rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{self.model.name}-trainedOn-{dataset.name}",
                        self.doc_uuid,
                    ),
                    from_=self.model.spdxId,
                    to=[dataset.spdxId],
                    relationshipType=spdx3.RelationshipType.trainedOn,
                    creationInfo=self.creation_info,
                )
                self.exporter.add_relationship(rel)

        # model testedOn validation datasets
        if self.model and self.validation_datasets:
            for dataset in self.validation_datasets:
                rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{self.model.name}-testedOn-{dataset.name}",
                        self.doc_uuid,
                    ),
                    from_=self.model.spdxId,
                    to=[dataset.spdxId],
                    relationshipType=spdx3.RelationshipType.testedOn,
                    creationInfo=self.creation_info,
                )
                self.exporter.add_relationship(rel)

        # output_dataset hasInput input_datasets (dataset lineage / preprocessing)
        if self.output_datasets and self.input_datasets:
            input_ids = [ds.spdxId for ds in self.input_datasets]
            for output_ds in self.output_datasets:
                rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{output_ds.name}-hasInput-sources",
                        self.doc_uuid,
                    ),
                    from_=output_ds.spdxId,
                    to=input_ids,
                    relationshipType=spdx3.RelationshipType.hasInput,
                    creationInfo=self.creation_info,
                )
                self.exporter.add_relationship(rel)

        output_path = Path(self.output_file)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.exporter.to_json(pretty=self.pretty))


# Global state holding the active shot
_active_shot: _ActiveShot | None = None  # pylint: disable=invalid-name


class Shoot(contextlib.ContextDecorator):
    """Context manager and decorator for capturing SPDX fragments.

    Each ``Shoot`` is one pass of the shuttle — a single recording session
    that weaves metadata about a model and its datasets into an SBOM fragment.

    Can be used as a context manager::

        with loom.shoot("fragments/train.spdx3.json") as shot:
            shot.set_model("my-model")
            shot.add_dataset("train.txt")
            shot.add_validation_dataset("valid.txt")
            # ... training code ...
            shot.set_model_hyperparameters({"lr": "0.1", "epoch": "5"})

    Or as a function decorator::

        @loom.shoot("fragments/preprocess.spdx3.json")
        def preprocess():
            loom.add_input_dataset("rawdata/neg.txt")
            loom.add_output_dataset("data/train.txt",
                                    data_preprocessing=["tokenization"])
    """

    def __init__(self, output_file: str | Path, pretty: bool = False):
        self.output_file = str(output_file)
        self.pretty = pretty
        self.previous_shot: _ActiveShot | None = None

    def __enter__(self) -> _ActiveShot:
        global _active_shot  # pylint: disable=global-statement
        self.previous_shot = _active_shot
        _active_shot = _ActiveShot(self.output_file, pretty=self.pretty)
        return _active_shot

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        global _active_shot  # pylint: disable=global-statement
        if _active_shot is not None:
            # Generate the fragment only if the code block executed successfully
            if exc_type is None:
                _active_shot.finalize()
        _active_shot = self.previous_shot


#: Lowercase alias for :class:`Shoot`
shoot = Shoot  # pylint: disable=invalid-name


def set_model(
    name: str,
    model_type: str | None = None,
    hyperparameters: dict[str, str] | None = None,
) -> None:
    """Set the name of the AI model being trained in the current shot."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.set_model()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.set_model(name, model_type=model_type, hyperparameters=hyperparameters)


def set_model_hyperparameters(hyperparameters: dict[str, str]) -> None:
    """Update the active model with hyperparameters captured after training."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.set_model_hyperparameters()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.set_model_hyperparameters(hyperparameters)


def add_dataset(name: str, dataset_type: str = "text") -> None:
    """Add a dataset utilized by the AI model in the current shot."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.add_dataset()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.add_dataset(name, dataset_type)


def add_validation_dataset(name: str, dataset_type: str = "text") -> None:
    """Add a validation/test dataset in the current shot."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.add_validation_dataset()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.add_validation_dataset(name, dataset_type)


def add_input_dataset(name: str, dataset_type: str = "text") -> None:
    """Declare a raw/source dataset consumed by a preprocessing step."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.add_input_dataset()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.add_input_dataset(name, dataset_type)


def add_output_dataset(
    name: str,
    dataset_type: str = "text",
    data_preprocessing: list[str] | None = None,
) -> None:
    """Declare a derived/processed dataset produced by a preprocessing step."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.add_output_dataset()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.add_output_dataset(name, dataset_type, data_preprocessing=data_preprocessing)
