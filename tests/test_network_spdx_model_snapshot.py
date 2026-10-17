# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The vendored SPDX model snapshot still equals what spdx.org serves (network).

Runs in the release gate (``PITLOOM_REQUIRE_NETWORK``), so a changed upstream
file blocks publishing until ``scripts/refresh_spdx_model_snapshot.py`` is run.

See also: tests/test_spdx_model_snapshot.py, tests/_network.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests._network import skip_on_network_error

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/refresh_spdx_model_snapshot.py"


@pytest.mark.network
def test_snapshot_matches_upstream() -> None:
    spec = importlib.util.spec_from_file_location("refresh_snapshot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with skip_on_network_error():
        names = module.drifted(
            module.DEFAULT_VERSION, module.SNAPSHOT_ROOT, module.fetch_url
        )
    assert names == [], "run scripts/refresh_spdx_model_snapshot.py"
