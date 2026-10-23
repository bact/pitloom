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
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._loom_caller import (
    _default_run_comment,
    _get_caller_info,
    _get_caller_script_path,
    _record_hyperparameter_provenance,
)
from pitloom._loom_dataset import LoomElements
from pitloom._loom_dataset_meta import read_sources
from pitloom._loom_model import LoomModels
from pitloom._sbom_io import write_text_lf
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.core.config import PitloomConfig
from pitloom.core.config_cascade import load_config_file
from pitloom.core.creation import CreationMetadata
from pitloom.core.model_extract_limit import require_max_dataset_hash_bytes
from pitloom.core.models import build_relationship
from pitloom.core.quote_source import quote_source
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.id_registry import IdRegistry, IdRegistrySession, resolve_registry
from pitloom.logging_config import configure_logging, one_line

log = logging.getLogger("pitloom.loom")

__all__ = [
    "_ActiveRun",
    "_default_run_comment",
    "_get_caller_info",
    "_get_caller_script_path",
    "_record_hyperparameter_provenance",
    "loom_config",
]


def loom_config(pitloom_config: PitloomConfig | str | Path | None) -> PitloomConfig:
    """The config of a loom run: *pitloom_config* itself, the file it names
    loaded like ``--config`` (a relative path from the current directory),
    else the defaults. Never an implicit ``[tool.pitloom]``.

    Raises:
        ValueError: the named file is missing, unreadable or invalid; the
            message names it.
    """
    if pitloom_config is None:
        return PitloomConfig()
    if isinstance(pitloom_config, PitloomConfig):
        return pitloom_config
    path = Path(pitloom_config)
    try:
        return load_config_file(path, source="pitloom_config")
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc
    except OSError as exc:
        raise ValueError(f"config file {quote_source(path)}: {one_line(exc)}") from exc


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
    ):
        # First: a declared-and-bad config or registry must fail before
        # _active_run is set (its caller assigns this constructor's result
        # directly to the module global -- an exception here means that
        # assignment never happens). Of the config, loom reads only the
        # registry (the id_registry argument wins), its update switch and
        # the dataset hash ceiling.
        configure_logging()
        config = loom_config(pitloom_config)
        resolved = resolve_registry(id_registry, config.id_registry, Path.cwd())
        max_hash_bytes = require_max_dataset_hash_bytes(
            config.max_dataset_hash_bytes, "pitloom_config"
        )
        self.update_id_registry: bool = config.update_id_registry
        self.output_file = output_file
        self.pretty = pretty
        self.doc_uuid = str(uuid4())
        self.session = IdRegistrySession(resolved)
        script_path = _get_caller_script_path()
        # (as captured, absolute now: the script may change directory)
        self.caller_script: tuple[str, Path] | None = (
            None
            if script_path is None
            else (script_path, Path(os.path.abspath(script_path)))
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
        self.elements = LoomElements(
            session=self.session,
            exporter=self.exporter,
            creation_info=self.creation_info,
            doc_uuid=self.doc_uuid,
            max_hash_bytes=max_hash_bytes,
        )
        self.models = LoomModels(
            session=self.session,
            exporter=self.exporter,
            creation_info=self.creation_info,
            doc_uuid=self.doc_uuid,
            update_id_registry=self.update_id_registry,
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
        sources state (:func:`~pitloom._loom_dataset_meta.read_sources`)."""
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
        data_preprocessing: list[str] | None = None,
        input_datasets: list[str] | None = None,
        *,
        croissant: str | os.PathLike[str] | None = None,
        declared_license: str | None = None,
    ) -> None:
        """Declare a derived/processed dataset produced by a preprocessing step."""
        dataset_pkg = self._build_dataset_package(
            name, dataset_type, croissant, declared_license
        )
        if data_preprocessing is not None:
            dataset_pkg.dataset_dataPreprocessing = data_preprocessing
            self.elements.declare_preprocessing(dataset_pkg)

        self._add_output(dataset_pkg, input_datasets)

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
        input_ids_by_name: dict[str | None, str] = {
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
        """Resolve the declared models, emit the relationships, write the
        fragment, then save the model ids the registry gained: the fragment
        first, so a failed write leaves no entry that no fragment carries.
        Last, the one ``INFO:`` counting the run's layout-alias hits."""
        self.model, self._model_generated = self.models.resolve()
        self._emit_model_dataset_relationships()
        self._emit_output_input_dataset_relationships()
        self._emit_script_file_and_generates()
        self.elements.finish()

        output_path = Path(self.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        write_text_lf(output_path, self.exporter.to_json(pretty=self.pretty))
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
