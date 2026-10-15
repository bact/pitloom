# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Caller inspection, provenance and registry-miss helpers for Loom runs.

See also: :mod:`pitloom._loom_active_run` for active run lifecycle and graph
building, :mod:`pitloom._loom_dataset` for dataset and file elements,
:mod:`pitloom._loom_model` for models.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import logging
from collections.abc import Callable
from pathlib import Path

from pitloom.__about__ import __version__
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    IdRegistrySession,
)
from pitloom.logging_config import field_loss_suffix, warn_once

log = logging.getLogger("pitloom.loom")

#: loom is a standalone SDK invoked from ad hoc scripts/notebooks, not
#: through a pyproject.toml-based [tool.pitloom.provenance] config -- so
#: provenance is always recorded both ways (Annotation + legacy comment)
#: rather than threading a format setting through the whole SDK surface.
LOOM_PROVENANCE_CONFIG = ProvenanceConfig(format="both")

#: Pitloom's own modules on the stack of a loom call; caller provenance
#: names the first frame outside them.
_SKIPPED_LOOM_FILENAMES = frozenset(
    {
        "loom.py",
        "_loom_active_run.py",
        "_loom_caller.py",
        "_loom_dataset.py",
        "_loom_model.py",
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


def warn_registry_miss(registry: IdRegistry, type_name: str, name: str) -> None:
    """The one ``WARNING:`` for a loom lookup of *name* under *type_name*
    that missed in *registry*: an entry under that type whose SHA-256 no
    longer matches (content changed); for a model, *name* held only under
    another type; else untracked. A dataset is not told about other types:
    its own file shares its name under ``software_File``."""
    if registry.get(type_name, name) is not None:
        log.warning(
            "loom: registry entry for %r exists but its SHA-256 no "
            "longer matches; minting a new spdxId (content changed).",
            name,
        )
    elif type_name == AI_PACKAGE_TYPE and registry.has_name(name):
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
    session: IdRegistrySession, type_name: str, name: str
) -> Callable[[], None] | None:
    """The *on_miss* of a loom lookup: :func:`warn_registry_miss` for
    *session*'s registry, or ``None`` when no registry is loaded (nothing
    is looked up)."""
    registry = session.registry
    if registry is None:
        return None
    return functools.partial(warn_registry_miss, registry, type_name, name)
