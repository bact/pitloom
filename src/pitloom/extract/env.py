# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for deployed environments using ``pipdeptree --json``."""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from typing import Any

from pitloom.core.internal_error import reraise_internal
from pitloom.core.project import ProjectMetadata
from pitloom.log_masking import masked_lines
from pitloom.messages.dependencies import (
    NO_DEPENDENCY_KEY,
    NO_OUTPUT,
    NO_PACKAGE_KEY,
    NOT_A_LIST,
    pipdeptree_exited,
    pipdeptree_not_json,
    pipdeptree_not_run,
    pipdeptree_shape,
)


def _last_line(stderr: bytes | None) -> str:
    """The last line of *stderr* that is not blank, stripped, or
    :data:`~pitloom.messages.dependencies.NO_OUTPUT`. *stderr* is masked
    whole before its last line is picked
    (:func:`~pitloom.log_masking.masked_lines`): a password holding a line
    break is not cut to its last piece."""
    lines = masked_lines((stderr or b"").decode("utf-8", "replace").strip())
    return lines[-1].strip() if lines else NO_OUTPUT


def _validated_node_list(data: Any) -> list[dict[str, Any]]:
    """Check *data* is ``pipdeptree --json``'s flat package list.

    Each node is ``{"package": {"key": ..., ...}, "dependencies": [{"key":
    ...}, ...]}``. ``--json-tree`` output (nested, no ``package`` wrapper)
    fails here rather than degrading into packages named ``unknown``.

    Raises:
        pitloom.messages.CodedRuntimeError: It is not
            (``environment-unreadable``).
    """
    if not isinstance(data, list):
        raise pipdeptree_shape(NOT_A_LIST)
    for node in data:
        package = node.get("package") if isinstance(node, dict) else None
        if not isinstance(package, dict) or not isinstance(package.get("key"), str):
            raise pipdeptree_shape(NO_PACKAGE_KEY)
        dependencies = node.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(dep, dict) and isinstance(dep.get("key"), str)
            for dep in dependencies
        ):
            raise pipdeptree_shape(NO_DEPENDENCY_KEY)
    return data


def _canonical_order(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return packages and their dependencies sorted by pipdeptree ``key``.

    pipdeptree does not document its output order, and the assembler's id
    numbering and registry claims follow input order. Ties (not seen from
    pipdeptree) break on version, then name.
    """
    ordered = sorted(
        data,
        key=lambda node: (
            node["package"]["key"],
            str(node["package"].get("installed_version", "")),
            str(node["package"].get("package_name", "")),
        ),
    )
    return [
        {**node, "dependencies": sorted(deps, key=lambda dep: dep["key"])}
        if isinstance(deps := node.get("dependencies"), list)
        else node
        for node in ordered
    ]


def read_environment() -> tuple[ProjectMetadata, list[dict[str, Any]]]:
    """Extract metadata for the deployed environment using pipdeptree.

    Runs ``pipdeptree --json``, which lists every installed package once
    with its direct dependencies; ``--json-tree``'s nested shape is not
    accepted.

    Returns:
        A tuple of (ProjectMetadata, list of package nodes from pipdeptree,
        sorted by ``key``).

    Raises:
        pitloom.messages.CodedRuntimeError: pipdeptree failed to run, or its
            output is not the expected ``--json`` list
            (``environment-unreadable``, a :class:`RuntimeError`).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pipdeptree", "--json"],
            capture_output=True,
            check=True,
        )  # nosec B603
    except subprocess.CalledProcessError as e:
        # The last stderr line names the cause (e.g. "No module named pipdeptree").
        raise pipdeptree_exited(e.returncode, _last_line(e.stderr)) from e
    except OSError as e:
        raise pipdeptree_not_run(e) from e
    try:
        # Bytes in: json.loads detects the encoding and skips a UTF-8 BOM.
        raw = json.loads(result.stdout)
    except ValueError as e:  # JSONDecodeError, UnicodeDecodeError
        reraise_internal(e)
        raise pipdeptree_not_json(e) from e
    tree = _canonical_order(_validated_node_list(raw))

    # Create a synthetic root package representing the environment
    metadata = ProjectMetadata(name="deployed-environment", version="0.0.0")
    metadata.description = "Deployed Python environment"

    # name/version are Pitloom's own placeholder for this synthetic root,
    # not values pipdeptree reported -- only the package list is.
    provenance = {
        "name": "Source: Pitloom generator | Method: synthetic environment root",
        "version": "Source: Pitloom generator | Method: synthetic environment root",
        "dependencies": "Source: pipdeptree",
    }
    metadata.provenance = provenance

    # The assembler consumes pipdeptree's flat package list directly.
    return metadata, tree
