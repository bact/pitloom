# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Internal implementation of the active :mod:`pitloom.loom` recording run.

See also: :mod:`pitloom._loom_caller` for stack inspection and provenance
helpers, :mod:`pitloom._loom_dataset` for dataset and file elements,
:mod:`pitloom._loom_model` for models (resolved at run exit), and
:mod:`pitloom.loom` for the public facade.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_args import check_sdk_arguments, loom_config
from pitloom._loom_caller import (
    _default_run_comment,
    _get_caller_info,
    _get_caller_script_path,
    _record_hyperparameter_provenance,
    cwd_relative_label,
)
from pitloom._loom_dataset import LoomElements
from pitloom._loom_dataset_meta import read_sources
from pitloom._loom_model import LoomModels
from pitloom._sbom_io import coded_write, write_text_lf
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.current_dir import current_dir
from pitloom.core.lfs_pointer import UnreadPointers
from pitloom.core.model_extract_limit import (
    require_max_dataset_hash_bytes,
    require_positive_ceiling,
)
from pitloom.core.models import build_relationship
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.id_registry import IdRegistry, IdRegistrySession, resolve_registry
from pitloom.logging_config import configure_logging
from pitloom.messages import FRAGMENT_USE, emit
from pitloom.messages.config import Parameter
from pitloom.messages.fragments import REFERENCE_NOT_FOUND_DATASET

log = logging.getLogger("pitloom.loom")

__all__ = [
    "_ActiveRun",
    "_default_run_comment",
    "_get_caller_info",
    "_get_caller_script_path",
    "_record_hyperparameter_provenance",
    "loom_config",
]


def _append_once(
    packages: list[spdx3.dataset_DatasetPackage], package: spdx3.dataset_DatasetPackage
) -> None:
    """Append *package* unless it is already in *packages*."""
    if not any(held is package for held in packages):
        packages.append(package)


# pylint: disable-next=too-many-instance-attributes
class _ActiveRun:
    """Internal state for an active BOM recording run."""

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        output_file: str,
        pretty: bool = False,
        creation_metadata: CreationMetadata | None = None,
        id_registry: str | Path | IdRegistry | None = None,
        *,
        pitloom_config: PitloomConfig | str | Path | None = None,
        max_dataset_hash_bytes: int | None = None,
        credentials: CredentialPolicy | None = None,
    ):
        # First: a declared-and-bad config or registry must fail before
        # _active_run is set (its caller assigns this constructor's result
        # directly to the module global -- an exception here means that
        # assignment never happens). Of the config, loom reads only the
        # registry (the id_registry argument wins), its update switch, the
        # dataset hash ceiling (the max_dataset_hash_bytes argument wins), the
        # credentials it accepts and its url-credentials mode (united with
        # the credentials argument, which can turn refusal on, never off).
        configure_logging()
        config = loom_config(pitloom_config)
        self.credentials = config.credential_policy.union(
            credentials or CredentialPolicy()
        )
        resolved = resolve_registry(
            id_registry,
            config.id_registry,
            current_dir(),
            refuse_credentials=self.credentials.refuse,
        )
        max_hash_bytes = (
            require_max_dataset_hash_bytes(
                config.max_dataset_hash_bytes,
                Parameter("PitloomConfig.max_dataset_hash_bytes"),
            )
            if max_dataset_hash_bytes is None
            else require_positive_ceiling(
                max_dataset_hash_bytes, Parameter("max_dataset_hash_bytes")
            )
        )
        self.update_id_registry: bool = config.update_id_registry
        self.output_file = output_file
        self.pretty = pretty
        self.doc_uuid = str(uuid4())
        self.session = IdRegistrySession(resolved)
        script_path = _get_caller_script_path()
        # Named as invoked; absolute now: the script may change directory.
        self.caller_script: tuple[str, Path] | None = (
            None
            if script_path is None
            else (cwd_relative_label(script_path), current_dir() / script_path)
        )
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
        # One per run (each __enter__ builds a new _ActiveRun): a run that
        # raised leaves nothing for the next.
        self.lfs_pointers = UnreadPointers()
        self.elements = LoomElements(
            session=self.session,
            exporter=self.exporter,
            creation_info=self.creation_info,
            doc_uuid=self.doc_uuid,
            max_hash_bytes=max_hash_bytes,
            pointers=self.lfs_pointers,
        )
        self.models = LoomModels(
            session=self.session,
            exporter=self.exporter,
            creation_info=self.creation_info,
            doc_uuid=self.doc_uuid,
            update_id_registry=self.update_id_registry,
            pointers=self.lfs_pointers,
        )

        #: The run's model: ``None`` until :meth:`finalize` resolves it.
        self.model: spdx3.ai_AIPackage | None = None
        self.datasets: list[spdx3.dataset_DatasetPackage] = []
        self.validation_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.input_datasets: list[spdx3.dataset_DatasetPackage] = []
        self.output_datasets: list[
            tuple[spdx3.dataset_DatasetPackage, list[str] | None]
        ] = []

    # pylint: disable-next=too-many-arguments
    def set_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
        generated: bool | None = None,
        *,
        path: str | os.PathLike[str] | None = None,
    ) -> None:
        """Declare the primary AI model being trained. *path*, its file, is
        hashed at run exit and gates its registry lookup (see
        :mod:`pitloom._loom_model`)."""
        check_sdk_arguments(
            ("name",),
            name=name,
            model_type=model_type,
            hyperparameters=hyperparameters,
            generated=generated,
            path=path,
        )
        self.models.declare(
            name,
            model_type=model_type,
            hyperparameters=hyperparameters,
            generated=generated,
            path=path,
            caller_info=_get_caller_info(),
        )

    def use_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
        *,
        path: str | os.PathLike[str] | None = None,
    ) -> None:
        """Declare the primary AI model being consumed/loaded by the current
        run; *path* as for :meth:`set_model`."""
        self.set_model(
            name,
            model_type=model_type,
            hyperparameters=hyperparameters,
            generated=False,
            path=path,
        )

    def set_model_hyperparameters(self, hyperparameters: dict[str, str]) -> None:
        """Update the last declared model with hyperparameters captured after
        training."""
        check_sdk_arguments(("hyperparameters",), hyperparameters=hyperparameters)
        self.models.set_hyperparameters(hyperparameters, _get_caller_info())

    def _build_dataset_package(
        self,
        name: str,
        dataset_type: str,
        croissant: str | os.PathLike[str] | None,
        declared_license: str | None,
    ) -> spdx3.dataset_DatasetPackage:
        """Build a ``dataset_DatasetPackage`` for *name* (see
        :meth:`~pitloom._loom_dataset.LoomElements.dataset`), with what its
        sources state (:func:`~pitloom._loom_dataset_meta.read_sources`),
        once its arguments are checked."""
        check_sdk_arguments(
            ("name", "dataset_type"),
            name=name,
            dataset_type=dataset_type,
            croissant=croissant,
            declared_license=declared_license,
        )
        caller_info = _get_caller_info()
        sources = read_sources(
            name,
            croissant=croissant,
            declared_license=declared_license,
            caller_info=caller_info,
        )
        return self.elements.dataset(name, dataset_type, caller_info, sources)

    def add_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        *,
        croissant: str | os.PathLike[str] | None = None,
        declared_license: str | None = None,
    ) -> None:
        """Add a dataset used for training in the current run."""
        _append_once(
            self.datasets,
            self._build_dataset_package(
                name, dataset_type, croissant, declared_license
            ),
        )

    def add_validation_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        *,
        croissant: str | os.PathLike[str] | None = None,
        declared_license: str | None = None,
    ) -> None:
        """Add a dataset used for validation/testing."""
        _append_once(
            self.validation_datasets,
            self._build_dataset_package(
                name, dataset_type, croissant, declared_license
            ),
        )

    def add_input_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        *,
        croissant: str | os.PathLike[str] | None = None,
        declared_license: str | None = None,
    ) -> None:
        """Declare a raw/source dataset consumed by a preprocessing step."""
        _append_once(
            self.input_datasets,
            self._build_dataset_package(
                name, dataset_type, croissant, declared_license
            ),
        )

    # pylint: disable-next=too-many-arguments
    def add_output_dataset(
        self,
        name: str,
        dataset_type: str = "text",
        data_preprocessing: list[str] | tuple[str, ...] | None = None,
        input_datasets: list[str] | tuple[str, ...] | None = None,
        *,
        croissant: str | os.PathLike[str] | None = None,
        declared_license: str | None = None,
    ) -> None:
        """Declare a derived/processed dataset produced by a preprocessing step."""
        check_sdk_arguments(
            (), data_preprocessing=data_preprocessing, input_datasets=input_datasets
        )
        dataset_pkg = self._build_dataset_package(
            name, dataset_type, croissant, declared_license
        )
        if data_preprocessing is not None:
            dataset_pkg.dataset_dataPreprocessing = list(data_preprocessing)
            self.elements.declare_preprocessing(dataset_pkg)

        self._add_output(
            dataset_pkg, None if input_datasets is None else list(input_datasets)
        )

    def _add_output(
        self, package: spdx3.dataset_DatasetPackage, sources: list[str] | None
    ) -> None:
        """Record *package* as an output. Declared again: its sources are
        the union, and ``None`` (every input) wins over a list."""
        for i, (held, held_sources) in enumerate(self.output_datasets):
            if held is package:
                if held_sources is not None:
                    merged = (
                        None
                        if sources is None
                        else list(dict.fromkeys([*held_sources, *sources]))
                    )
                    self.output_datasets[i] = (package, merged)
                return
        self.output_datasets.append((package, sources))

    def _relate(
        self, from_id: str | None, to_ids: list[str], rel_type: str, **kwargs: Any
    ) -> None:
        """Add the relationship *rel_type* from *from_id* to *to_ids* (none
        without a *from_id*); *kwargs* as for
        :func:`~pitloom.core.models.build_relationship`."""
        rel = build_relationship(
            from_id=from_id,
            to_ids=to_ids,
            rel_type=rel_type,
            doc_name="loom",
            doc_uuid=self.doc_uuid,
            creation_info=self.creation_info,
            **kwargs,
        )
        if rel:
            self.exporter.add_relationship(rel)

    def _emit_model_dataset_relationships(self) -> None:
        """Emit trainedOn and testedOn relationships for models and datasets."""
        if not self.model:
            return
        for datasets, rel_type in (
            (self.datasets, spdx3.RelationshipType.trainedOn),
            (self.validation_datasets, spdx3.RelationshipType.testedOn),
        ):
            for dataset in datasets:
                self._relate(self.model.spdxId, [require_spdx_id(dataset)], rel_type)

    def _resolve_input_ids_for_output(
        self,
        wanted_names: list[str] | None,
        all_input_ids: list[str],
        input_ids_by_name: dict[str, str],
        output_ds_name: str | None,
    ) -> list[str]:
        """Resolve specific input IDs requested by an output dataset; each
        name no input was declared under is said once, in first-seen
        order."""
        if wanted_names is None:
            return all_input_ids
        input_ids: list[str] = []
        for wanted_name in dict.fromkeys(wanted_names):
            input_id = input_ids_by_name.get(wanted_name)
            if input_id is None:
                emit(
                    log,
                    REFERENCE_NOT_FOUND_DATASET,
                    logging.WARNING,
                    dataset=output_ds_name,
                    dataset_input=wanted_name,
                )
                continue
            input_ids.append(input_id)
        return input_ids

    def _emit_output_input_dataset_relationships(self) -> None:
        """Emit hasInput relationships between output and input datasets."""
        if not self.output_datasets:
            return
        all_input_ids = [require_spdx_id(ds) for ds in self.input_datasets]
        input_ids_by_name: dict[str, str] = {
            name: require_spdx_id(ds)
            for ds in self.input_datasets
            for name in self.elements.names_of(ds)
        }
        for output_ds, wanted_names in self.output_datasets:
            input_ids = [
                i
                for i in self._resolve_input_ids_for_output(
                    wanted_names, all_input_ids, input_ids_by_name, output_ds.name
                )
                if i != output_ds.spdxId  # declared as input and output
            ]
            if not input_ids:
                continue
            self._relate(
                from_id=output_ds.spdxId,
                to_ids=input_ids,
                rel_type=spdx3.RelationshipType.hasInput,
            )

    def finalize(self) -> None:
        """Resolve the declared models, emit the relationships, write the
        fragment, then save the model ids the registry gained: the fragment
        first, so a failed write leaves no entry that no fragment carries.
        Once the fragment is written, the one ``WARNING:`` for the Git LFS
        pointers it records by their ``oid``; last, the one ``INFO:``
        counting the run's layout-alias hits."""
        self.model, self._model_generated = self.models.resolve()
        self._emit_model_dataset_relationships()
        self._emit_output_input_dataset_relationships()
        self._emit_script_file_and_generates()
        self.elements.finish()

        # Serialised first: a refused fragment creates no directory or file.
        fragment_json = self.exporter.to_json(
            pretty=self.pretty, credentials=self.credentials
        )
        output_path = Path(self.output_file)
        with coded_write(self.output_file, use=FRAGMENT_USE):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_lf(output_path, fragment_json)
        self.lfs_pointers.warn()
        self.models.persist()
        self.session.info_layout_alias_hits()

    def _emit_script_file_and_generates(self) -> None:
        """Emit a ``software_File`` for the calling script and relationships."""
        if self.caller_script is None:
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

        script_file = self.elements.script_file(*self.caller_script)
        script_id = require_spdx_id(script_file)

        if generates_model and self.model is not None:
            self._relate(
                from_id=script_id,
                to_ids=[require_spdx_id(self.model)],
                rel_type=spdx3.RelationshipType.generates,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.build,
            )
        elif self.model is not None and not generates_model:
            self._relate(
                from_id=script_id,
                to_ids=[require_spdx_id(self.model)],
                rel_type=spdx3.RelationshipType.hasDataFile,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.runtime,
            )

        if output_targets:
            self._relate(
                from_id=script_id,
                to_ids=output_targets,
                rel_type=spdx3.RelationshipType.generates,
                rel_class=spdx3.LifecycleScopedRelationship,
                scope=spdx3.LifecycleScopeType.build,
            )
