# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Internal implementation of the active :mod:`pitloom.loom` recording run.

See also: :mod:`pitloom._loom_caller` for stack inspection and provenance helpers,
and :mod:`pitloom.loom` for the public facade.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

# pylint: disable-next=cyclic-import
from pitloom import loom
from pitloom._loom_caller import (
    _default_run_comment,
    _get_caller_info,
    _get_caller_script_path,
    _hash_and_registry_lookup,
    _record_hyperparameter_provenance,
    _resolve_registry,
)
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.provenance import emit_provenance
from pitloom.core.creation import CreationMetadata
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.ids import IdRegistry

log = logging.getLogger("pitloom.loom")

__all__ = [
    "_ActiveRun",
    "_default_run_comment",
    "_get_caller_info",
    "_get_caller_script_path",
    "_hash_and_registry_lookup",
    "_record_hyperparameter_provenance",
    "_resolve_registry",
]


# pylint: disable=too-many-instance-attributes
class _ActiveRun:
    """Internal state for an active BOM recording run."""

    def __init__(
        self,
        output_file: str,
        pretty: bool = False,
        creation_metadata: CreationMetadata | None = None,
        registry: str | Path | IdRegistry | None = None,
    ):
        self.output_file = output_file
        self.pretty = pretty
        self.doc_uuid = str(uuid4())
        self.registry = _resolve_registry(registry)
        self.caller_script_path = _get_caller_script_path()
        self._model_generated: bool | None = None

        self.creation_info, agents, tools = build_creation_info(
            creation_metadata or CreationMetadata(),
            "pitloom-sdk",
            self.doc_uuid,
            default_comment=_default_run_comment(),
        )

        self.exporter = Spdx3JsonExporter()
        for agent in agents:
            self.exporter.add_agent(agent)
        for tool in tools:
            self.exporter.object_set.add(tool)

        self.model: spdx3.ai_AIPackage | None = None
        self.datasets: list[spdx3.dataset_DatasetPackage] = []
        self.validation_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.input_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.output_datasets: list[
            tuple[spdx3.dataset_DatasetPackage, list[str] | None]
        ] = []

    def set_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
        generated: bool | None = None,
    ) -> None:
        """Define the primary AI model being trained."""
        caller_info = _get_caller_info()
        registered_id = None
        if self.registry is not None:
            registered_id = self.registry.lookup_entity(name, "ai_AIPackage")
            if registered_id is None:
                if name in self.registry.entities:
                    log.warning(
                        "loom: registry entry for entity %r exists but under a "
                        "different type; minting a new spdxId.",
                        name,
                    )
                else:
                    log.warning(
                        "loom: entity %r not found in registry; minting a new spdxId "
                        "(untracked entity).",
                        name,
                    )
        self.model = spdx3.ai_AIPackage(
            spdxId=registered_id or generate_spdx_id("AIPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
        )
        self._model_generated = generated
        if model_type is not None:
            self.model.ai_typeOfModel = [model_type]
        provenance: dict[str, str] = {"package": caller_info}
        if hyperparameters is not None:
            self.model.ai_hyperparameter = [
                spdx3.DictionaryEntry(key=k, value=v)
                for k, v in hyperparameters.items()
            ]
            _record_hyperparameter_provenance(provenance, hyperparameters, caller_info)
        self.exporter.add_package(self.model)
        emit_provenance(
            subject=self.model,
            provenance=provenance,
            creation_info=self.creation_info,
            doc_name=name,
            doc_uuid=self.doc_uuid,
            exporter=self.exporter,
            # pylint: disable-next=protected-access
            provenance_config=loom._LOOM_PROVENANCE_CONFIG,
        )

    def use_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
    ) -> None:
        """Define the primary AI model being consumed/loaded by the current run."""
        self.set_model(
            name,
            model_type=model_type,
            hyperparameters=hyperparameters,
            generated=False,
        )

    def set_model_hyperparameters(self, hyperparameters: dict[str, str]) -> None:
        """Update the active model with hyperparameters captured after training."""
        if self.model is None:
            raise RuntimeError(
                "No model set. Call set_model() before set_model_hyperparameters()."
            )
        self.model.ai_hyperparameter = [
            spdx3.DictionaryEntry(key=k, value=v) for k, v in hyperparameters.items()
        ]
        provenance: dict[str, str] = {}
        _record_hyperparameter_provenance(
            provenance, hyperparameters, _get_caller_info()
        )
        emit_provenance(
            subject=self.model,
            provenance=provenance,
            creation_info=self.creation_info,
            doc_name=self.model.name or "model",
            doc_uuid=self.doc_uuid,
            exporter=self.exporter,
            # pylint: disable-next=protected-access
            provenance_config=loom._LOOM_PROVENANCE_CONFIG,
        )

    def _build_dataset_package(
        self, name: str, dataset_type: str
    ) -> spdx3.dataset_DatasetPackage:
        """Build a ``dataset_DatasetPackage`` for *name*."""
        caller_info = _get_caller_info()
        hash_element, registered_id = _hash_and_registry_lookup(name, self.registry)
        dataset_pkg = spdx3.dataset_DatasetPackage(
            spdxId=registered_id
            or generate_spdx_id("DatasetPackage", name, self.doc_uuid),
            name=name,
            creationInfo=self.creation_info,
        )
        emit_provenance(
            subject=dataset_pkg,
            provenance={"package": caller_info},
            creation_info=self.creation_info,
            doc_name=name,
            doc_uuid=self.doc_uuid,
            exporter=self.exporter,
            # pylint: disable-next=protected-access
            provenance_config=loom._LOOM_PROVENANCE_CONFIG,
        )
        if hash_element is not None:
            dataset_pkg.verifiedUsing = [hash_element]

        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]
        return dataset_pkg

    def add_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for training in the current run."""
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        self.datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_validation_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for validation/testing."""
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        self.validation_datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_input_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Declare a raw/source dataset consumed by a preprocessing step."""
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        self.input_datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_output_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        data_preprocessing: list[str] | None = None,
        input_datasets: list[str] | None = None,
    ) -> None:
        """Declare a derived/processed dataset produced by a preprocessing step."""
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        if data_preprocessing is not None:
            dataset_pkg.dataset_dataPreprocessing = data_preprocessing

        self.output_datasets.append((dataset_pkg, input_datasets))
        self.exporter.add_package(dataset_pkg)

    def _emit_model_dataset_relationships(self) -> None:
        """Emit trainedOn and testedOn relationships for models and datasets."""
        if not self.model:
            return
        for dataset in self.datasets:
            rel = build_relationship(
                from_id=self.model.spdxId,
                to_ids=[require_spdx_id(dataset)],
                rel_type=spdx3.RelationshipType.trainedOn,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
            )
            if rel:
                self.exporter.add_relationship(rel)

        for dataset in self.validation_datasets:
            rel = build_relationship(
                from_id=self.model.spdxId,
                to_ids=[require_spdx_id(dataset)],
                rel_type=spdx3.RelationshipType.testedOn,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
            )
            if rel:
                self.exporter.add_relationship(rel)

    def _resolve_input_ids_for_output(
        self,
        wanted_names: list[str] | None,
        all_input_ids: list[str],
        input_ids_by_name: dict[str | None, str],
        output_ds_name: str | None,
    ) -> list[str]:
        """Resolve specific input IDs requested by an output dataset."""
        if wanted_names is None:
            return all_input_ids
        input_ids: list[str] = []
        for wanted_name in wanted_names:
            input_id = input_ids_by_name.get(wanted_name)
            if input_id is None:
                log.warning(
                    "loom: add_output_dataset(%r) names input_datasets=%r "
                    "as a source, but no add_input_dataset(%r) was "
                    "declared in this run; skipping it.",
                    output_ds_name,
                    wanted_name,
                    wanted_name,
                )
                continue
            input_ids.append(input_id)
        return input_ids

    def _emit_output_input_dataset_relationships(self) -> None:
        """Emit hasInput relationships between output and input datasets."""
        if not (self.output_datasets and self.input_datasets):
            return
        all_input_ids = [require_spdx_id(ds) for ds in self.input_datasets]
        input_ids_by_name = {ds.name: require_spdx_id(ds) for ds in self.input_datasets}
        for output_ds, wanted_names in self.output_datasets:
            input_ids = self._resolve_input_ids_for_output(
                wanted_names, all_input_ids, input_ids_by_name, output_ds.name
            )
            if not input_ids:
                continue
            rel = build_relationship(
                from_id=output_ds.spdxId,
                to_ids=input_ids,
                rel_type=spdx3.RelationshipType.hasInput,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
            )
            if rel:
                self.exporter.add_relationship(rel)

    def finalize(self) -> None:
        """Finalize the run and output the SBOM fragment."""
        self._emit_model_dataset_relationships()
        self._emit_output_input_dataset_relationships()
        self._emit_script_file_and_generates()

        output_path = Path(self.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.exporter.to_json(pretty=self.pretty))

    def _emit_script_file_and_generates(self) -> None:
        """Emit a ``software_File`` for the calling script and relationships."""
        script_path = self.caller_script_path
        if script_path is None:
            return

        if self.model is not None:
            generates_model = (
                self._model_generated
                if self._model_generated is not None
                else bool(self.datasets)
            )
        else:
            generates_model = False

        output_targets = sorted(require_spdx_id(ds) for ds, _ in self.output_datasets)

        if self.model is None and not output_targets:
            return

        script_file = self._build_script_file(script_path)
        self.exporter.add_file(script_file)
        script_id = require_spdx_id(script_file)

        if generates_model and self.model is not None:
            rel1 = build_relationship(
                from_id=script_id,
                to_ids=[require_spdx_id(self.model)],
                rel_type=spdx3.RelationshipType.generates,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.build,
            )
            if rel1:
                self.exporter.add_relationship(rel1)
        elif self.model is not None and not generates_model:
            rel2 = build_relationship(
                from_id=script_id,
                to_ids=[require_spdx_id(self.model)],
                rel_type=spdx3.RelationshipType.hasDataFile,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.runtime,
            )
            if rel2:
                self.exporter.add_relationship(rel2)

        if output_targets:
            rel3 = build_relationship(
                from_id=script_id,
                to_ids=output_targets,
                rel_type=spdx3.RelationshipType.generates,
                doc_name="loom",
                doc_uuid=self.doc_uuid,
                creation_info=self.creation_info,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.build,
            )
            if rel3:
                self.exporter.add_relationship(rel3)

    def _build_script_file(self, script_path: str) -> spdx3.software_File:
        """Build the ``software_File`` for the generating script."""
        hash_element, registered_id = _hash_and_registry_lookup(
            script_path, self.registry
        )
        script_file = spdx3.software_File(
            spdxId=registered_id
            or generate_spdx_id("File", script_path, self.doc_uuid),
            name=script_path,
            creationInfo=self.creation_info,
        )
        script_file.software_fileKind = spdx3.software_FileKindType.file
        if hash_element is not None:
            script_file.verifiedUsing = [hash_element]
        return script_file
