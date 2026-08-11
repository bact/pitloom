# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom SDK for capturing BOM fragments during external script/notebook execution."""

import contextlib
import hashlib
import inspect
import logging
import types
from pathlib import Path
from uuid import uuid4

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.assemble.spdx3.creation_info import build_creation_info
from pitloom.assemble.spdx3.provenance import emit_provenance
from pitloom.core.creation import CreationMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.ids import IdRegistry

#: loom.py is a standalone SDK invoked from ad hoc scripts/notebooks, not
#: through a pyproject.toml-based [tool.pitloom.provenance] config -- so
#: provenance is always recorded both ways (Annotation + legacy comment)
#: rather than threading a format setting through the whole SDK surface.
_LOOM_PROVENANCE_CONFIG = ProvenanceConfig(format="both")

log = logging.getLogger(__name__)


def _get_caller_info() -> str:
    """Find the first caller frame outside of the pitloom.loom module."""
    try:
        for frame_info in inspect.stack():
            if frame_info.filename != __file__:
                p = Path(frame_info.filename).absolute()
                try:
                    filename = p.relative_to(Path.cwd()).as_posix()
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
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.debug("Failed to determine caller info: %s", exc)
    return "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"


def _get_caller_script_path() -> str | None:
    """Return the cwd-relative POSIX path of the script that opened the
    active :class:`Run`.

    Skips frames inside ``pitloom.loom`` and ``contextlib`` -- the latter
    appears as the immediate caller when ``loom.run`` is used as a function
    decorator, since ``contextlib.ContextDecorator.__call__`` enters the
    context manager (calling ``Run.__enter__``, where this is invoked)
    *before* the wrapped function itself is called, so the wrapped
    function's own frame does not exist yet.

    Returns ``None`` when no on-disk script file can be identified relative
    to the current working directory -- e.g. a REPL or Jupyter notebook
    frame -- since there is no generating script to attribute a
    ``generates`` relationship to.
    """
    try:
        for frame_info in inspect.stack():
            filename = frame_info.filename
            if filename in (__file__, contextlib.__file__):
                continue
            if filename.startswith("<"):
                return None
            path = Path(filename)
            if not path.is_file():
                return None
            try:
                return path.resolve().relative_to(Path.cwd()).as_posix()
            except ValueError:
                return path.as_posix()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        log.debug("Failed to determine caller script path: %s", exc)
    return None


def _default_run_comment() -> str:
    """Default CreationInfo.comment for a fragment: source and tool version."""
    return f"Generated via Pitloom loom SDK v{__version__} (script/notebook capture)"


def _record_hyperparameter_provenance(
    provenance: dict[str, str], hyperparameters: dict[str, str], caller_info: str
) -> None:
    """Record exact per-key provenance for *hyperparameters*, same as the
    extractors' dict-valued fields (``properties``, ``hyperparameters``) --
    not one shared note for the whole dict.

    Unlike :func:`~pitloom.extract._extract_utils.record_dict_field_provenance`,
    *caller_info* is not sanitized here: it is Pitloom's own compound
    ``"Source: ... | Method: ..."`` string, not untrusted artifact text, and
    sanitizing it would mangle its own intentional ``|`` separator. Only the
    hyperparameter key -- which does come from the caller's own dict -- is
    sanitized before interpolation.
    """
    for key, _value in hyperparameters.items():
        safe_key = sanitize_provenance_text(str(key))
        provenance[f"hyperparameters.{key}"] = f"{caller_info} | Field: {safe_key}"


def _resolve_registry(
    registry: str | Path | IdRegistry | None,
) -> IdRegistry | None:
    """Resolve the *registry* argument of :class:`Run` to an
    :class:`~pitloom.ids.IdRegistry` or ``None``.

    An :class:`IdRegistry` instance is used as-is. A path (``str``/``Path``)
    is loaded explicitly. ``None`` auto-discovers ``loom-ids.json`` by
    walking up from the current working directory. Any load failure is
    logged and degrades to "no registry" rather than raising -- a missing or
    broken registry must never break a training/preprocessing run.
    """
    if isinstance(registry, IdRegistry):
        return registry
    if registry is not None:
        try:
            return IdRegistry.load(Path(registry))
        except (FileNotFoundError, ValueError, OSError) as exc:
            log.warning("loom: could not load registry %s: %s", registry, exc)
            return None
    return IdRegistry.find()


def _hash_and_registry_lookup(
    name: str, registry: IdRegistry | None
) -> tuple[spdx3.Hash | None, str | None]:
    """Compute a SHA-256 ``Hash`` element for *name* when it is an existing
    file, and resolve its registered ``spdxId`` when a registry is given.

    Returns ``(hash_element_or_None, registered_spdx_id_or_None)``.  A
    registry hash mismatch against *name* (the file changed since the
    registry entry was written) is logged as a warning; the caller then
    mints a fresh id -- changed content is different provenance truth and
    must not be silently glossed over.
    """
    path = Path(name)
    if not path.is_file():
        return None, None

    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    hash_element = spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=sha256)

    registered_id: str | None = None
    if registry is not None:
        registered_id = registry.lookup_file(name, sha256)
        if registered_id is None:
            if name in registry.files:
                log.warning(
                    "loom: registry entry for %r exists but its SHA-256 no "
                    "longer matches; minting a new spdxId (content changed).",
                    name,
                )
            else:
                log.warning(
                    "loom: file %r not found in registry; minting a new spdxId "
                    "(untracked file).",
                    name,
                )
    return hash_element, registered_id


class _ActiveRun:  # pylint: disable=too-many-instance-attributes
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
        # Read-only consultation: loom never writes back to the registry.
        self.registry = _resolve_registry(registry)
        self.caller_script_path = _get_caller_script_path()
        self._model_generated: bool | None = None

        # Same CreationMetadata handling as the CLI and build hook: a named
        # creator becomes the matching Agent subclass, otherwise the
        # SoftwareAgent "Pitloom" is the createdBy actor, with the Tool
        # "Pitloom" in createdUsing. Unattended capture defaults the comment
        # to the loom-SDK note.
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
        # (dataset, explicit input names it derives from -- None means "every
        # input_dataset declared in this run", the original all-inputs
        # behaviour; see add_output_dataset).
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
        """Define the primary AI model being trained.

        Args:
            name: Model name or file path.
            model_type: Type of model, e.g. ``"supervised"``,
                ``"text-classification"``.
            hyperparameters: Key-value pairs of hyperparameters known at
                declaration time. Use :meth:`set_model_hyperparameters` to
                update after training completes.
            generated: Whether the calling script should get a ``generates``
                relationship to this model. ``None`` (default) infers it:
                the script is considered to generate the model when the run
                also declares training datasets via :meth:`add_dataset`
                (e.g. a training run) but not otherwise (e.g. an
                evaluation-only run). Pass ``True``/``False`` to override
                the inference explicitly.
        """
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
            provenance_config=_LOOM_PROVENANCE_CONFIG,
        )

    def use_model(
        self,
        name: str,
        model_type: str | None = None,
        hyperparameters: dict[str, str] | None = None,
    ) -> None:
        """Define the primary AI model being consumed/loaded by the current run.

        This explicitly records the model as a runtime dependency (creates a
        ``hasDataFile`` relationship) rather than a generated artifact.
        """
        self.set_model(
            name,
            model_type=model_type,
            hyperparameters=hyperparameters,
            generated=False,
        )

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
            provenance_config=_LOOM_PROVENANCE_CONFIG,
        )

    def _build_dataset_package(
        self, name: str, dataset_type: str
    ) -> spdx3.dataset_DatasetPackage:
        """Build a ``dataset_DatasetPackage`` for *name*, consulting the
        registry and attaching a SHA-256 ``verifiedUsing`` hash when *name*
        is an existing file (enables merge-time hash-fallback unification
        even when no registry is in play)."""
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
            provenance_config=_LOOM_PROVENANCE_CONFIG,
        )
        if hash_element is not None:
            dataset_pkg.verifiedUsing = [hash_element]

        dt = getattr(
            spdx3.dataset_DatasetType, dataset_type, spdx3.dataset_DatasetType.text
        )
        dataset_pkg.dataset_datasetType = [dt]
        return dataset_pkg

    def add_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for training in the current run.

        Creates a ``trainedOn`` relationship from the model to this dataset.
        For the validation set use :meth:`add_validation_dataset`.
        For raw input datasets in a preprocessing step use :meth:`add_input_dataset`.
        """
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        self.datasets.append(dataset_pkg)
        self.exporter.add_package(dataset_pkg)

    def add_validation_dataset(self, name: str, dataset_type: str = "text") -> None:
        """Add a dataset used for validation/testing.

        Creates a ``testedOn`` relationship from the model to this dataset.

        Args:
            name: Dataset name or file path.
            dataset_type: SPDX 3 dataset type string, e.g. ``"text"``, ``"image"``.
        """
        dataset_pkg = self._build_dataset_package(name, dataset_type)
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
        """Declare a derived/processed dataset produced by a preprocessing step.

        Use together with :meth:`add_input_dataset` to record dataset lineage.
        Creates ``hasInput`` relationships from this dataset to input datasets
        declared in this run.

        Args:
            name: Dataset name or file path.
            dataset_type: SPDX 3 dataset type string, e.g. ``"text"``, ``"image"``.
            data_preprocessing: List of preprocessing steps applied, e.g.
                ``["thai-text-normalization", "newmm-word-tokenization"]``.
            input_datasets: Names of the specific :meth:`add_input_dataset`
                calls this output derives from. Defaults to ``None``, which
                links to *every* input dataset declared in the run -- correct
                for a run that preprocesses one batch into one output. Pass an
                explicit subset when a single run accumulates more than one
                independent preprocessing stage (e.g. one run producing
                train/valid/test splits, each from its own raw files), so
                each output's ``hasInput`` lineage stays scoped to only the
                inputs it actually came from, instead of every input the run
                has seen so far.
        """
        dataset_pkg = self._build_dataset_package(name, dataset_type)
        if data_preprocessing is not None:
            dataset_pkg.dataset_dataPreprocessing = data_preprocessing

        self.output_datasets.append((dataset_pkg, input_datasets))
        self.exporter.add_package(dataset_pkg)

    def finalize(self) -> None:
        """Finalize the run and output the SBOM fragment."""
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
                    to=[require_spdx_id(dataset)],
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
                    to=[require_spdx_id(dataset)],
                    relationshipType=spdx3.RelationshipType.testedOn,
                    creationInfo=self.creation_info,
                )
                self.exporter.add_relationship(rel)

        # output_dataset hasInput input_datasets (dataset lineage / preprocessing)
        if self.output_datasets and self.input_datasets:
            all_input_ids = [require_spdx_id(ds) for ds in self.input_datasets]
            input_ids_by_name = {
                ds.name: require_spdx_id(ds) for ds in self.input_datasets
            }
            for output_ds, wanted_names in self.output_datasets:
                if wanted_names is None:
                    input_ids = all_input_ids
                else:
                    input_ids = []
                    for wanted_name in wanted_names:
                        input_id = input_ids_by_name.get(wanted_name)
                        if input_id is None:
                            log.warning(
                                "loom: add_output_dataset(%r) names input_datasets=%r "
                                "as a source, but no add_input_dataset(%r) was "
                                "declared in this run; skipping it.",
                                output_ds.name,
                                wanted_name,
                                wanted_name,
                            )
                            continue
                        input_ids.append(input_id)
                if not input_ids:
                    continue
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

        self._emit_script_file_and_generates()

        output_path = Path(self.output_file)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.exporter.to_json(pretty=self.pretty))

    def _emit_script_file_and_generates(self) -> None:
        """Emit a ``software_File`` for the calling script plus ``generates``
        relationships to the model and/or output datasets it produced.

        No orphan script Files: nothing is emitted when the caller could not
        be identified (see :func:`_get_caller_script_path`) or when neither
        a model nor output datasets end up connected to it.
        """
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

        # `generates` is scoped `build`: the script producing this model or
        # these datasets is a build-time step (training/preprocessing), not
        # something that runs as part of the shipped artifact -- contrast
        # with the `hasDataFile` usage relationship the AI-model scanner
        # emits for a runtime consumer like predict.py loading model.bin
        # (see pitloom.assemble.spdx3.ai), which is scoped `runtime`.
        if generates_model and self.model is not None:
            self.exporter.add_relationship(
                spdx3.LifecycleScopedRelationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{script_path}-generates-{self.model.name}",
                        self.doc_uuid,
                    ),
                    from_=script_id,
                    to=[require_spdx_id(self.model)],
                    relationshipType=spdx3.RelationshipType.generates,
                    scope=spdx3.LifecycleScopeType.build,
                    creationInfo=self.creation_info,
                )
            )
        elif self.model is not None and not generates_model:
            self.exporter.add_relationship(
                spdx3.LifecycleScopedRelationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{script_path}-hasDataFile-{self.model.name}",
                        self.doc_uuid,
                    ),
                    from_=script_id,
                    to=[require_spdx_id(self.model)],
                    relationshipType=spdx3.RelationshipType.hasDataFile,
                    scope=spdx3.LifecycleScopeType.runtime,
                    creationInfo=self.creation_info,
                )
            )

        if output_targets:
            self.exporter.add_relationship(
                spdx3.LifecycleScopedRelationship(
                    spdxId=generate_spdx_id(
                        "Relationship",
                        f"{script_path}-generates-outputs",
                        self.doc_uuid,
                    ),
                    from_=script_id,
                    to=output_targets,
                    relationshipType=spdx3.RelationshipType.generates,
                    scope=spdx3.LifecycleScopeType.build,
                    creationInfo=self.creation_info,
                )
            )

    def _build_script_file(self, script_path: str) -> spdx3.software_File:
        """Build the ``software_File`` for the generating script, consulting
        the registry and attaching a SHA-256 hash when the script exists on
        disk -- the same identity system the Hatchling build hook uses for
        the packaged copy of this same file (see
        :func:`pitloom.assemble.spdx3.document._add_package_files`), so the
        two become literally the same element once merged."""
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


# Global state holding the active run
_active_run: _ActiveRun | None = None  # pylint: disable=invalid-name


class Run(contextlib.ContextDecorator):
    """Context manager and decorator for capturing SPDX fragments.

    Each ``Run`` is a single recording session that weaves metadata about
    a model and its datasets into an SBOM fragment.

    Can be used as a context manager::

        with loom.run("fragments/train.spdx3.json") as run:
            run.set_model("my-model")
            run.add_dataset("train.txt")
            run.add_validation_dataset("valid.txt")
            # ... training code ...
            run.set_model_hyperparameters({"lr": "0.1", "epoch": "5"})

    Or as a function decorator::

        @loom.run("fragments/preprocess.spdx3.json")
        def preprocess():
            loom.add_input_dataset("rawdata/neg.txt")
            loom.add_output_dataset("data/train.txt",
                                    data_preprocessing=["tokenization"])

    The fragment's SPDX ``CreationInfo`` is configurable on par with the CLI
    and Hatchling build hook: pass a ``CreationMetadata`` to name a creator
    (a person, organization, or automated agent), or override the tool,
    timestamp, and comment. With none given, the fragment records the
    ``SoftwareAgent`` "Pitloom" (createdBy) and ``Tool`` "Pitloom"
    (createdUsing) of an unattended run::

        loom.run(
            "fragments/train.spdx3.json",
            creation_metadata=CreationMetadata(
                creators=[Creator(name="Alice", type="person")]
            ),
        )

    Args:
        output_file: Path to write the SBOM fragment to.
        pretty: Indent the JSON output with 2 spaces when ``True``.
        creation_metadata: Creator, tool, timestamp, and comment overrides for
            the fragment's ``CreationInfo``. See :class:`CreationMetadata` for
            all fields. When ``None`` (default), the comment defaults to an
            auto-generated note identifying the loom SDK and its version,
            and the creator defaults to the ``SoftwareAgent`` "Pitloom".
        registry: A :class:`~pitloom.ids.IdRegistry`, a path to a registry
            JSON file, or ``None`` (default) to auto-discover
            ``loom-ids.json`` by walking up from the current working
            directory. Consulted read-only: datasets, the model, and the
            generating script all get the registered ``spdxId`` when one
            exists for them, so independently generated fragments can be
            unified at merge time without name-based matching.
    """

    def __init__(
        self,
        output_file: str | Path,
        pretty: bool = False,
        creation_metadata: CreationMetadata | None = None,
        registry: str | Path | IdRegistry | None = None,
    ):
        self.output_file = str(output_file)
        self.pretty = pretty
        self.creation_metadata = creation_metadata or CreationMetadata()
        self.registry = registry
        self.previous_run: _ActiveRun | None = None

    def __enter__(self) -> _ActiveRun:
        global _active_run  # pylint: disable=global-statement
        self.previous_run = _active_run
        _active_run = _ActiveRun(
            self.output_file,
            pretty=self.pretty,
            creation_metadata=self.creation_metadata,
            registry=self.registry,
        )
        return _active_run

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        global _active_run  # pylint: disable=global-statement
        if _active_run is not None:
            # Generate the fragment only if the code block executed successfully
            if exc_type is None:
                _active_run.finalize()
        _active_run = self.previous_run


#: Lowercase alias for :class:`Run`
run = Run  # pylint: disable=invalid-name


def set_model(
    name: str,
    model_type: str | None = None,
    hyperparameters: dict[str, str] | None = None,
    generated: bool | None = None,
) -> None:
    """Set the name of the AI model being trained in the current run."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use `loom.set_model()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.set_model(
        name,
        model_type=model_type,
        hyperparameters=hyperparameters,
        generated=generated,
    )


def use_model(
    name: str,
    model_type: str | None = None,
    hyperparameters: dict[str, str] | None = None,
) -> None:
    """Explicitly declare an AI model consumed by the current run (for inference)."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use `loom.use_model()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.use_model(
        name,
        model_type=model_type,
        hyperparameters=hyperparameters,
    )


def set_model_hyperparameters(hyperparameters: dict[str, str]) -> None:
    """Update the active model with hyperparameters captured after training."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use `loom.set_model_hyperparameters()`"
            " inside a `with pitloom.loom.run():` block or decorated function."
        )
    _active_run.set_model_hyperparameters(hyperparameters)


def add_dataset(name: str, dataset_type: str = "text") -> None:
    """Add a dataset utilized by the AI model in the current run."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use `loom.add_dataset()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.add_dataset(name, dataset_type)


def add_validation_dataset(name: str, dataset_type: str = "text") -> None:
    """Add a validation/test dataset in the current run."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use "
            "`loom.add_validation_dataset()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.add_validation_dataset(name, dataset_type)


def add_input_dataset(name: str, dataset_type: str = "text") -> None:
    """Declare a raw/source dataset consumed by a preprocessing step."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use "
            "`loom.add_input_dataset()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.add_input_dataset(name, dataset_type)


def add_output_dataset(
    name: str,
    dataset_type: str = "text",
    data_preprocessing: list[str] | None = None,
    input_datasets: list[str] | None = None,
) -> None:
    """Declare a derived/processed dataset produced by a preprocessing step."""
    if _active_run is None:
        raise RuntimeError(
            "No active loom.run() found. Please use "
            "`loom.add_output_dataset()` inside a "
            "`with pitloom.loom.run():` block or decorated function."
        )
    _active_run.add_output_dataset(
        name,
        dataset_type,
        data_preprocessing=data_preprocessing,
        input_datasets=input_datasets,
    )
