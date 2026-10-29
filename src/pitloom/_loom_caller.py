# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Caller inspection, provenance, hash and registry-miss helpers for Loom
runs.

See also: :mod:`pitloom._loom_active_run` for active run lifecycle and graph
building, :mod:`pitloom._loom_dataset` for dataset and file elements,
:mod:`pitloom._loom_model` for models.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import logging
import os
from collections.abc import Callable
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.core.file_hash import HexDigests
from pitloom.core.lfs_pointer import LFS_POINTER_METHOD, LfsPointer
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import file_hashes, lfs_pointer_hashes
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    IdRegistrySession,
)
from pitloom.logging_config import field_loss_suffix, warn_once

log = logging.getLogger("pitloom.loom")

#: loom is a standalone SDK invoked from ad hoc scripts/notebooks, not
#: through a pyproject.toml-based [tool.pitloom.provenance] config -- so
#: provenance is always recorded both ways (Annotation + comment)
#: rather than threading a format setting through the whole SDK surface.
LOOM_PROVENANCE_CONFIG = ProvenanceConfig(format="both")

#: The provenance field of a ``verifiedUsing`` copied from a Git LFS
#: pointer's ``oid``; its value is :func:`pointer_provenance`.
POINTER_PROVENANCE_FIELD = "verified_using"

#: Pitloom's own modules on the stack of a loom call; caller provenance
#: names the first frame outside them.
_SKIPPED_LOOM_FILENAMES = frozenset(
    {
        "loom.py",
        "_loom_active_run.py",
        "_loom_caller.py",
        "_loom_dataset.py",
        "_loom_dataset_keys.py",
        "_loom_model.py",
    }
)


def cwd_relative_label(location: str | os.PathLike[str]) -> str:
    """*location* as provenance names it: a POSIX path from the current
    directory when it lies below it, else its bare name, so no machine path
    is recorded and the label does not depend on where the project lies. A
    ``..`` is resolved as the OS opens the path (through symlinks), any
    other path lexically. A label only: open *location* as given."""
    text = os.fspath(location)
    if ".." in Path(text).parts:
        absolute, base = os.path.realpath(text), os.path.realpath(os.getcwd())
    else:
        absolute, base = os.path.abspath(text), os.getcwd()
    try:
        return Path(absolute).relative_to(base).as_posix()
    except ValueError:
        return Path(absolute).name


def _get_caller_info() -> str:
    """Find the first caller frame outside of the pitloom.loom module."""
    try:
        for frame_info in inspect.stack():
            frame_path = Path(frame_info.filename)
            if frame_path.name not in _SKIPPED_LOOM_FILENAMES:
                filename = cwd_relative_label(frame_info.filename)

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
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        # WARNING once per process, DEBUG after -- inspect.stack() failing
        # is a per-process environment condition (sandboxed/frozen
        # interpreter), not a one-off, so it would otherwise repeat on
        # every loom call in a training loop.
        warn_once(
            log,
            "caller_info",
            "Failed to determine caller info: %s"
            + field_loss_suffix(
                "degraded",
                "provenance Source (falls back to 'unknown'; Method: "
                "inspect_caller is still recorded)",
            ),
            exc,
        )
    return "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"


def _get_caller_script_path() -> str | None:
    """The path of the script that opened the active Run: POSIX and relative to
    the current directory when below it, else absolute (a label, not a path
    to open: see :func:`cwd_relative_label`)."""
    try:
        for frame_info in inspect.stack():
            filename = frame_info.filename
            if (
                Path(filename).name in _SKIPPED_LOOM_FILENAMES
                or filename == contextlib.__file__
            ):
                continue
            if filename.startswith("<"):
                return None
            path = Path(filename)
            if not path.is_file():
                return None
            try:
                return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
            except ValueError:
                return path.as_posix()
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        warn_once(
            log,
            "caller_script_path",
            "Failed to determine caller script path: %s"
            + field_loss_suffix("skipped", "caller_script_path"),
            exc,
        )
    return None


def _default_run_comment() -> str:
    """Default CreationInfo.comment for a fragment."""
    return f"Generated via Pitloom loom SDK v{__version__} (script/notebook capture)"


def _record_hyperparameter_provenance(
    provenance: dict[str, str], hyperparameters: dict[str, str], caller_info: str
) -> None:
    """Record exact per-key provenance for hyperparameters, in key order."""
    for key in sorted(hyperparameters):
        safe_key = sanitize_provenance_text(str(key))
        provenance[f"hyperparameters.{key}"] = f"{caller_info} | Field: {safe_key}"


#: What a loom message calls an element of each registry type.
_TYPE_WORDS = {
    AI_PACKAGE_TYPE: "model",
    DATASET_PACKAGE_TYPE: "dataset package",
    FILE_TYPE: "file",
}


def warn_registry_miss(
    registry: IdRegistry,
    type_name: str,
    name: str,
    *,
    by_path: bool = False,
    unhashed: bool = False,
) -> None:
    """The one ``WARNING:`` for a loom lookup of *name* under *type_name*
    that missed in *registry*: an entry under that type whose SHA-256 no
    longer matches (content changed); for a model, *name* held only under
    another type; else untracked. A dataset is not told about other types:
    its own file shares its name under ``software_File``. With *by_path*,
    *name* is a path key, which a model's own ``software_File`` shares:
    never told about other types either. The changed-content line names
    the element's type: a dataset's package and file share a name. With
    *unhashed* (no content was hashed), an entry recording a SHA-256 says
    so instead: it cannot be vouched for."""
    entry = registry.get(type_name, name)
    if entry is not None and unhashed:
        log.warning(
            "loom: registry entry for %s %r records a SHA-256 but no content "
            "was hashed; minting a new spdxId.",
            _TYPE_WORDS.get(type_name, "entity"),
            name,
        )
    elif entry is not None:
        log.warning(
            "loom: registry entry for %s %r exists but its SHA-256 no "
            "longer matches; minting a new spdxId (content changed).",
            _TYPE_WORDS.get(type_name, "entity"),
            name,
        )
    elif type_name == AI_PACKAGE_TYPE and not by_path and registry.has_name(name):
        log.warning(
            "loom: registry entry for entity %r exists but under a "
            "different type; minting a new spdxId.",
            name,
        )
    else:
        kind = "file" if type_name == FILE_TYPE else "entity"
        log.warning(
            "loom: %s %r not found in registry; minting a new spdxId (untracked %s).",
            kind,
            name,
            kind,
        )


def registry_miss_callback(
    session: IdRegistrySession,
    type_name: str,
    name: str,
    *,
    by_path: bool = False,
    unhashed: bool = False,
) -> Callable[[], None] | None:
    """The *on_miss* of a loom lookup: :func:`warn_registry_miss` for
    *session*'s registry, or ``None`` when no registry is loaded (nothing
    is looked up)."""
    registry = session.registry
    if registry is None:
        return None
    return functools.partial(
        warn_registry_miss,
        registry,
        type_name,
        name,
        by_path=by_path,
        unhashed=unhashed,
    )


def stated_hashes(digests: HexDigests, pointer: LfsPointer | None) -> list[spdx3.Hash]:
    """The ``verifiedUsing`` of a file loom hashed, or of the package
    standing for it: *pointer*'s when the file is a Git LFS pointer, else
    *digests*."""
    if pointer is not None:
        return lfs_pointer_hashes(pointer)
    return file_hashes(digests)


def pointer_provenance(label: str) -> str:
    """The provenance of a hash copied from the Git LFS pointer *label*
    names (:func:`cwd_relative_label`, taken when the path was given), for
    :data:`POINTER_PROVENANCE_FIELD`."""
    return f"Source: {sanitize_provenance_text(label)} | Method: {LFS_POINTER_METHOD}"
