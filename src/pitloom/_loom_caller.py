# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Caller inspection and provenance helpers for Loom runs.

See also: :mod:`pitloom._loom_active_run` for active run lifecycle and graph building.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import logging
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.__about__ import __version__
from pitloom.extract._extract_utils import sanitize_provenance_text, warn_once
from pitloom.ids import IdRegistry, resolve_registry

log = logging.getLogger("pitloom.loom")

_SKIPPED_LOOM_FILENAMES = frozenset(
    {
        "loom.py",
        "_loom_active_run.py",
        "_loom_caller.py",
    }
)


def _get_caller_info() -> str:
    """Find the first caller frame outside of the pitloom.loom module."""
    try:
        for frame_info in inspect.stack():
            frame_path = Path(frame_info.filename)
            if frame_path.name not in _SKIPPED_LOOM_FILENAMES:
                p = frame_path.absolute()
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
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        # WARNING once per process, DEBUG after -- inspect.stack() failing
        # is a per-process environment condition (sandboxed/frozen
        # interpreter), not a one-off, so it would otherwise repeat on
        # every loom call in a training loop.
        warn_once(
            log,
            "caller_info",
            "Failed to determine caller info: %s | Field(s) affected "
            "(degraded): provenance Source (falls back to 'unknown'; "
            "Method: inspect_caller is still recorded)",
            exc,
        )
    return "Source: unknown | Method: inspect_caller (tool: pitloom.loom)"


def _get_caller_script_path() -> str | None:
    """Return the cwd-relative POSIX path of the script that opened the active Run."""
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
                return path.resolve().relative_to(Path.cwd()).as_posix()
            except ValueError:
                return path.as_posix()
    # pylint: disable=broad-exception-caught
    except Exception as exc:
        warn_once(
            log,
            "caller_script_path",
            "Failed to determine caller script path: %s | Field(s) "
            "affected (skipped): caller_script_path",
            exc,
        )
    return None


def _default_run_comment() -> str:
    """Default CreationInfo.comment for a fragment."""
    return f"Generated via Pitloom loom SDK v{__version__} (script/notebook capture)"


def _record_hyperparameter_provenance(
    provenance: dict[str, str], hyperparameters: dict[str, str], caller_info: str
) -> None:
    """Record exact per-key provenance for hyperparameters."""
    for key, _value in hyperparameters.items():
        safe_key = sanitize_provenance_text(str(key))
        provenance[f"hyperparameters.{key}"] = f"{caller_info} | Field: {safe_key}"


def _resolve_registry(
    registry: str | Path | IdRegistry | None,
) -> IdRegistry | None:
    """Resolve the registry argument of Run to an IdRegistry or None."""
    return resolve_registry(Path.cwd(), registry)


def _hash_and_registry_lookup(
    name: str, registry: IdRegistry | None
) -> tuple[spdx3.Hash | None, str | None]:
    """Compute SHA-256 Hash for *name* and resolve its registered spdxId."""
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
