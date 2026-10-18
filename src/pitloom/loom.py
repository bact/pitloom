# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom SDK for capturing BOM fragments during external script/notebook execution.

See also: :mod:`pitloom._loom_active_run`, where the active-run recording
state (:class:`_ActiveRun` and its helpers) lives; this module is the
public facade.
"""

import contextlib
import os
import types
from pathlib import Path

from pitloom._loom_active_run import _ActiveRun
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.core.models import _clear_doc_counters
from pitloom.id_registry import IdRegistry

# Global state holding the active run
# pylint: disable=invalid-name
_active_run: _ActiveRun | None = None


class Run(contextlib.ContextDecorator):
    """Context manager and decorator for capturing SPDX fragments.

    Each ``Run`` is a single recording session that weaves metadata about
    a model and its datasets into an SBOM fragment.

    Can be used as a context manager::

        with loom.run("fragments/train.spdx3.json") as run:
            run.set_model("my-model", path="model.bin")
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
            the fragment's ``CreationInfo``. See ``CreationMetadata`` for
            all fields. When ``None`` (default), the comment defaults to an
            auto-generated note identifying the loom SDK and its version,
            and the creator defaults to the ``SoftwareAgent`` "Pitloom".
        id_registry: A ``pitloom.id_registry.IdRegistry``, a path to a
            registry JSON file (relative to the current working
            directory), or ``None`` (default): the config's
            ``id-registry``, else no registry -- never searched for.
            Datasets, their files, the model, and the generating script
            all get the registered ``spdxId`` when one exists for them, so
            independently generated fragments can be unified at merge time
            without name-based matching. Loom writes one kind of entry: a
            model declared with ``path=`` whose file the registry does not
            know, saved when the run ends, after the fragment.
        pitloom_config: A ``pitloom.core.config.PitloomConfig``, or a path
            to a config file read like ``--config`` (relative to the
            current working directory; missing or invalid raises
            ``ValueError``), or ``None`` (default): the built-in defaults.
            No ``[tool.pitloom]`` is ever read implicitly. Loom reads only
            ``max-dataset-hash-bytes``, ``id-registry`` (when *id_registry*
            is not given; a relative path in a config file is relative to
            that file's directory) and ``update-id-registry`` (``false``:
            no model is registered). Every other key does not apply to
            loom.
    """

    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        output_file: str | Path,
        pretty: bool = False,
        creation_metadata: CreationMetadata | None = None,
        id_registry: str | Path | IdRegistry | None = None,
        *,
        pitloom_config: PitloomConfig | str | Path | None = None,
    ):
        self.output_file = str(output_file)
        self.pretty = pretty
        self.creation_metadata = creation_metadata or CreationMetadata()
        self.id_registry = id_registry
        self.pitloom_config = pitloom_config
        #: The run active at the latest ``__enter__``.
        self.previous_run: _ActiveRun | None = None
        #: One per open ``__enter__``: a recursive ``@loom.run`` function
        #: re-enters this object before the outer call exits.
        self._outer_runs: list[_ActiveRun | None] = []

    def __enter__(self) -> _ActiveRun:
        # pylint: disable=global-statement
        global _active_run
        self.previous_run = _active_run
        self._outer_runs.append(_active_run)
        _active_run = _ActiveRun(
            self.output_file,
            pretty=self.pretty,
            creation_metadata=self.creation_metadata,
            id_registry=self.id_registry,
            pitloom_config=self.pitloom_config,
        )
        return _active_run

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        # pylint: disable=global-statement
        global _active_run
        current = _active_run
        try:
            # Generate the fragment only if the code block executed successfully
            if current is not None and exc_type is None:
                current.finalize()
        finally:
            # The doc_uuid is a fresh uuid4 no later run reuses, so nothing
            # else would clear its _ID_COUNTERS entries (unlike a deterministic
            # doc_uuid's build() call): clear on every path.
            if current is not None:
                _clear_doc_counters(current.doc_uuid)
            _active_run = self._outer_runs.pop() if self._outer_runs else None


#: Lowercase alias for :class:`Run`
# pylint: disable=invalid-name
run = Run


def _no_active_run(call: str) -> RuntimeError:
    """The error for *call* outside a ``loom.run()``."""
    return RuntimeError(
        f"No active loom.run() found. Please use `loom.{call}()` inside a "
        "`with pitloom.loom.run():` block or decorated function."
    )


def set_model(
    name: str,
    model_type: str | None = None,
    hyperparameters: dict[str, str] | None = None,
    generated: bool | None = None,
    *,
    path: str | os.PathLike[str] | None = None,
) -> None:
    """Declare the AI model being trained in the current run.

    Resolved when the run ends without an exception: *path*, the model's
    file (relative to the current directory at this call), is then hashed;
    with a registry, the hash gates the lookup of the file's path key (of
    *name* outside the registry's root), and a model the registry does not
    know is registered. Without a usable *path*, *name* is looked up
    ungated. A file rewritten in between is a new model with a new id.
    """
    if _active_run is None:
        raise _no_active_run("set_model")
    _active_run.set_model(
        name,
        model_type=model_type,
        hyperparameters=hyperparameters,
        generated=generated,
        path=path,
    )


def use_model(
    name: str,
    model_type: str | None = None,
    hyperparameters: dict[str, str] | None = None,
    *,
    path: str | os.PathLike[str] | None = None,
) -> None:
    """Explicitly declare an AI model consumed by the current run (for
    inference); *path* as for :func:`set_model`."""
    if _active_run is None:
        raise _no_active_run("use_model")
    _active_run.use_model(
        name,
        model_type=model_type,
        hyperparameters=hyperparameters,
        path=path,
    )


def set_model_hyperparameters(hyperparameters: dict[str, str]) -> None:
    """Update the active model with hyperparameters captured after training."""
    if _active_run is None:
        raise _no_active_run("set_model_hyperparameters")
    _active_run.set_model_hyperparameters(hyperparameters)


def add_dataset(
    name: str,
    dataset_type: str = "text",
    *,
    croissant: str | os.PathLike[str] | None = None,
    declared_license: str | None = None,
) -> None:
    """Add a dataset utilized by the AI model in the current run.

    Args:
        name: The dataset: a file, a directory, or a name for one that is
            not local. A directory's dataset card (the YAML frontmatter of
            its ``README.md``) is read for its ``license`` (with
            ``license_name``/``license_link`` for ``other``), ``version``
            and ``tags``.
        dataset_type: An SPDX ``dataset_DatasetType`` name.
        croissant: A local Croissant JSON-LD file describing the dataset;
            its licence, version, description, creator and other dataset
            fields are written onto the package, each with its provenance.
            A URL raises ``ValueError``: loom reads no network source.
        declared_license: The dataset's licence (an SPDX expression or
            other text) as the caller declares it. It wins over a Croissant
            file's, which wins over a dataset card's. A source's
            ``unknown``, ``NOASSERTION`` or blank licence is no licence.

    Raises:
        ValueError: *croissant* is a URL, or cannot be read as Croissant.
    """
    if _active_run is None:
        raise _no_active_run("add_dataset")
    _active_run.add_dataset(
        name, dataset_type, croissant=croissant, declared_license=declared_license
    )


def add_validation_dataset(
    name: str,
    dataset_type: str = "text",
    *,
    croissant: str | os.PathLike[str] | None = None,
    declared_license: str | None = None,
) -> None:
    """Add a validation/test dataset in the current run; arguments as for
    :func:`add_dataset`."""
    if _active_run is None:
        raise _no_active_run("add_validation_dataset")
    _active_run.add_validation_dataset(
        name, dataset_type, croissant=croissant, declared_license=declared_license
    )


def add_input_dataset(
    name: str,
    dataset_type: str = "text",
    *,
    croissant: str | os.PathLike[str] | None = None,
    declared_license: str | None = None,
) -> None:
    """Declare a raw/source dataset consumed by a preprocessing step;
    arguments as for :func:`add_dataset`."""
    if _active_run is None:
        raise _no_active_run("add_input_dataset")
    _active_run.add_input_dataset(
        name, dataset_type, croissant=croissant, declared_license=declared_license
    )


# pylint: disable-next=too-many-arguments
def add_output_dataset(
    name: str,
    dataset_type: str = "text",
    data_preprocessing: list[str] | None = None,
    input_datasets: list[str] | None = None,
    *,
    croissant: str | os.PathLike[str] | None = None,
    declared_license: str | None = None,
) -> None:
    """Declare a derived/processed dataset produced by a preprocessing step.

    *data_preprocessing* wins over a source's; *input_datasets* names the
    ``add_input_dataset()`` declarations it derives from (``None``: all);
    the other arguments as for :func:`add_dataset`."""
    if _active_run is None:
        raise _no_active_run("add_output_dataset")
    _active_run.add_output_dataset(
        name,
        dataset_type,
        data_preprocessing=data_preprocessing,
        input_datasets=input_datasets,
        croissant=croissant,
        declared_license=declared_license,
    )
