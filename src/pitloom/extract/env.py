# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for deployed environments using pipdeptree."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from pitloom.core.project import ProjectMetadata


def read_environment() -> tuple[ProjectMetadata, list[dict[str, Any]]]:
    """Extract metadata for the deployed environment using pipdeptree.

    Returns:
        A tuple of (ProjectMetadata, list of package nodes from pipdeptree).
    """
    try:
        result = subprocess.run(
            ["pipdeptree", "--json-tree", "--all"],
            capture_output=True,
            text=True,
            check=True,
        )
        tree = json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"Failed to run pipdeptree: {e}") from e

    # Create a synthetic root package representing the environment
    metadata = ProjectMetadata(name="deployed-environment", version="0.0.0")
    metadata.description = "Deployed Python environment"

    # name/version are Pitloom's own placeholder for this synthetic root,
    # not values pipdeptree reported -- only the dependency tree is.
    provenance = {
        "name": "Source: Pitloom generator | Method: synthetic environment root",
        "version": "Source: Pitloom generator | Method: synthetic environment root",
        "dependencies": "Source: pipdeptree",
    }
    metadata.provenance = provenance

    # The assembler consumes the raw pipdeptree tree structure directly.
    return metadata, tree
