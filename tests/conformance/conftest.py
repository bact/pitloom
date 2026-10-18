# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for the conformance tests (G7, CISA 2026, FSCT 2024, BSI): each
scenario SBOM built once."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conformance.g7ai_shared import SCENARIOS


@pytest.fixture(name="sboms", scope="session")
def sboms_fixture(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Scenario name -> path of its generated SBOM."""
    root = tmp_path_factory.mktemp("g7ai-scenarios")
    paths = {}
    # A session fixture runs before the per-test socket block: block it here.
    with patch("socket.socket", side_effect=OSError("network blocked")):
        for name, build in SCENARIOS.items():
            paths[name] = root / f"{name}.spdx3.json"
            paths[name].write_text(build(), encoding="utf-8")
    return paths
