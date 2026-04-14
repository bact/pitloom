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

from spdx_python_model.bindings import v3_0_1 as spdx3

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
        self.creation_info.createdBy = [person.spdxId]  # type: ignore[attr-defined, assignment]  # pylint: disable=line-too-long  # noqa: E501

        self.exporter = Spdx3JsonExporter()
        self.exporter.add_person(person)

        self.model: spdx3.ai_AIPackage | None = None
        self.datasets: list[spdx3.dataset_DatasetPackage] = []

    def set_model(self, name: str) -> None:
        """Define the primary AI Model being trained."""
        caller_info = _get_caller_info()
        self.model = spdx3.ai_AIPackage(
            spdxId=generate_spdx_id("AIPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )
        self.exporter.add_package(self.model)

    def add_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for training or validation."""
        caller_info = _get_caller_info()
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
            comment=f"Metadata provenance: package: {caller_info}",
        )

        # Map simple string types to spdx3.dataset_DatasetType enums dynamically
        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]  # type: ignore[assignment]

        self.datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def finalize(self) -> None:
        """Finalize the shot and output the SBOM fragment."""
        if self.model and self.datasets:
            for dataset in self.datasets:
                rel = spdx3.Relationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{self.model.name}-trainedOn-{dataset.name}",
                        self.doc_uuid,
                    ),
                    from_=self.model.spdxId,  # type: ignore[attr-defined]
                    to=[dataset.spdxId],  # type: ignore[attr-defined]
                    relationshipType=spdx3.RelationshipType.trainedOn,
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

        with loom.shoot("fragments/model.spdx3.json") as shot:
            shot.set_model("my-model")
            shot.add_dataset("my-dataset")

    Or as a function decorator::

        @loom.shoot("fragments/model.spdx3.json")
        def train():
            loom.set_model("my-model")
            loom.add_dataset("my-dataset")
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


def set_model(name: str) -> None:
    """Set the name of the AI model being trained in the current shot."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.set_model()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.set_model(name)


def add_dataset(name: str, dataset_type: str = "text") -> None:
    """Add a dataset utilized by the AI model in the current shot."""
    if _active_shot is None:
        raise RuntimeError(
            "No active shot found. Please use `loom.add_dataset()` inside a "
            "`with pitloom.loom.shoot():` block or decorated function."
        )
    _active_shot.add_dataset(name, dataset_type)
