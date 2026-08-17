# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom SDK for capturing BOM fragments during external script/notebook execution.

See also: :mod:`pitloom._loom_active_run`, where the active-run recording
state (:class:`_ActiveRun` and its helpers) lives -- this module is the
public facade and re-exports what it needs from there.
"""

import contextlib
import types
from pathlib import Path

from pitloom._loom_active_run import _ActiveRun
from pitloom.core.creation import CreationMetadata
from pitloom.core.provenance import ProvenanceConfig
from pitloom.ids import IdRegistry

#: loom.py is a standalone SDK invoked from ad hoc scripts/notebooks, not
#: through a pyproject.toml-based [tool.pitloom.provenance] config -- so
#: provenance is always recorded both ways (Annotation + legacy comment)
#: rather than threading a format setting through the whole SDK surface.
_LOOM_PROVENANCE_CONFIG = ProvenanceConfig(format="both")


# Global state holding the active run
# pylint: disable=invalid-name
_active_run: _ActiveRun | None = None


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
            the fragment's ``CreationInfo``. See ``CreationMetadata`` for
            all fields. When ``None`` (default), the comment defaults to an
            auto-generated note identifying the loom SDK and its version,
            and the creator defaults to the ``SoftwareAgent`` "Pitloom".
        registry: A ``pitloom.ids.IdRegistry``, a path to a registry
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
        # pylint: disable=global-statement
        global _active_run
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
        # pylint: disable=global-statement
        global _active_run
        if _active_run is not None:
            # Generate the fragment only if the code block executed successfully
            if exc_type is None:
                _active_run.finalize()
        _active_run = self.previous_run


#: Lowercase alias for :class:`Run`
# pylint: disable=invalid-name
run = Run


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
