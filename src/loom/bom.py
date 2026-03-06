# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Loom SDK for capturing BOM fragments during external script/notebook execution."""

import contextlib
import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from spdx_python_model import v3_0_1 as spdx3

from loom.core.models import generate_spdx_id
from loom.exporters.spdx3_json import Spdx3JsonExporter

_logger = logging.getLogger(__name__)


def _apply_metadata_sources(
    dataset_pkg: spdx3.dataset_DatasetPackage,
    metadata_sources: dict[str, str],
) -> None:
    """Apply metadata from external sources to a DatasetPackage in-place.

    Each key in ``metadata_sources`` names a source type, and each value is
    the URL or file path for that source.  Unknown source types are logged as
    warnings so they are visible without halting execution.

    Supported source types:

    - ``"croissant"`` — a Croissant JSON-LD document
      (requires ``pip install 'loom[croissant]'``)

    Args:
        dataset_pkg: The SPDX dataset package to enrich.
        metadata_sources: Mapping of source-type name to URL or file path.
    """
    for source_type, source_location in metadata_sources.items():
        if source_type == "croissant":
            _apply_croissant_source(dataset_pkg, source_location)
        else:
            _logger.warning(
                "Unknown metadata source type %r for dataset %r; skipping.",
                source_type,
                dataset_pkg.name,
            )


def _apply_croissant_source(
    dataset_pkg: spdx3.dataset_DatasetPackage, source: str
) -> None:
    """Enrich a DatasetPackage in-place with metadata from a Croissant document.

    Logs a warning and returns without modification if ``mlcroissant`` is not
    installed or the document cannot be loaded.

    Args:
        dataset_pkg: The SPDX dataset package to enrich.
        source: URL or file path to a Croissant JSON-LD document.
    """
    try:
        from loom.extractors.croissant import (
            enrich_dataset_package,
            extract_croissant_metadata,
        )

        croissant_meta = extract_croissant_metadata(source)
        enrich_dataset_package(dataset_pkg, croissant_meta)
    except ImportError:
        _logger.warning(
            "mlcroissant is not installed; skipping Croissant enrichment for %r. "
            "Install it with: pip install 'loom[croissant]'",
            dataset_pkg.name,
        )
    except Exception as exc:
        _logger.warning(
            "Failed to enrich dataset %r from Croissant source %r: %s",
            dataset_pkg.name,
            source,
            exc,
        )


def _get_caller_info() -> str:
    """Find the first caller frame outside of the loom.bom module."""
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
                        f"Method: inspect_caller (tool: loom.bom, "
                        f"function: <module>)"
                    )
                return (
                    f"Source: {filename} | "
                    f"Method: inspect_caller (tool: loom.bom, "
                    f"function: {func_name})"
                )
    except Exception:
        pass
    return "Source: unknown | Method: inspect_caller (tool: loom.bom)"


class _ActiveRun:
    """Internal state for an active BOM tracking run."""

    def __init__(self, output_file: str):
        self.output_file = output_file
        self.doc_uuid = str(uuid4())

        self.creation_info = spdx3.CreationInfo(
            specVersion="3.0.1", created=datetime.now(timezone.utc)
        )
        # Create a default Agent to satisfy the createdBy constraint
        person = spdx3.Person(
            spdxId=generate_spdx_id("Person", "loom-sdk", self.doc_uuid),
            name="Loom SDK (Automated Run)",
            creationInfo=self.creation_info,
        )
        self.creation_info.createdBy = [person.spdxId]

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

    def add_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        metadata_sources: dict[str, str] | None = None,
    ) -> None:
        """Add a dataset to the current BOM tracking run.

        Args:
            name: The dataset name.
            dataset_type: One of the SPDX ``DatasetType`` enum values
                (e.g. ``"text"``, ``"image"``). Defaults to ``"text"``.
            metadata_sources: Optional mapping of source-type names to URLs or
                file paths. Each entry is used to enrich the SPDX dataset
                package with additional metadata.  Supported source types:
                ``"croissant"`` (Croissant JSON-LD). Unknown types are logged
                as warnings and skipped.
        """
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
        dataset_pkg.dataset_datasetType = [dt]

        if metadata_sources:
            _apply_metadata_sources(dataset_pkg, metadata_sources)

        self.datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def finalize(self) -> None:
        """Finalize the run and output the SBOM fragment."""
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

        output_path = Path(self.output_file)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.exporter.to_json())


# Global state holding the active run
_active_run: _ActiveRun | None = None


class track(contextlib.ContextDecorator):
    """Context manager and decorator for capturing SPDX fragments.

    Can be used as a context manager (`with track(output_file=...):`)
    or as a function decorator (`@track(output_file=...)`).
    """

    def __init__(self, output_file: str | Path):
        self.output_file = str(output_file)
        self.previous_run = None

    def __enter__(self):
        global _active_run
        self.previous_run = _active_run
        _active_run = _ActiveRun(self.output_file)
        return _active_run

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _active_run
        if _active_run is not None:
            # Generate the fragment only if the code block executed successfully
            if exc_type is None:
                _active_run.finalize()
        _active_run = self.previous_run
        return False


def set_model(name: str) -> None:
    """Set the name of the AI model being trained in the current run."""
    if _active_run is None:
        raise RuntimeError(
            "No active run found. Please use `bom.set_model()` inside a "
            "`with loom.bom.track():` block or decorated function."
        )
    _active_run.set_model(name)


def add_dataset(
    name: str,
    dataset_type: str = "text",
    metadata_sources: dict[str, str] | None = None,
) -> None:
    """Add a dataset to the current BOM tracking run.

    Args:
        name: The dataset name.
        dataset_type: One of the SPDX ``DatasetType`` enum values
            (e.g. ``"text"``, ``"image"``). Defaults to ``"text"``.
        metadata_sources: Optional mapping of source-type names to URLs or
            file paths used to enrich the SPDX dataset package. Example::

                metadata_sources={"croissant": "https://example.com/data.json"}

            Supported source types: ``"croissant"`` (Croissant JSON-LD).
            Unknown types are logged as warnings and skipped.
    """
    if _active_run is None:
        raise RuntimeError(
            "No active run found. Please use `bom.add_dataset()` inside a "
            "`with loom.bom.track():` block or decorated function."
        )
    _active_run.add_dataset(name, dataset_type, metadata_sources)
