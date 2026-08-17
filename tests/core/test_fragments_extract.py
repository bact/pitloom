# ruff: noqa: F403, F405
from __future__ import annotations

import json
import logging

import pytest

from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import *


def test_missing_fragment_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    """A fragment file that does not exist must be skipped with a warning."""
    exporter = Spdx3JsonExporter()
    with caplog.at_level(logging.WARNING, logger="pitloom.assemble.spdx3.fragments"):
        merge_fragments(
            _FRAGMENTS_DIR,
            ["nonexistent-fragment.spdx3.json"],
            exporter,
        )
    # Object set must be empty -- nothing merged
    data = json.loads(exporter.to_json())
    graph = data.get("@graph", [])
    assert len(graph) == 0

    # Warning must have been emitted
    assert any("nonexistent-fragment" in r.message for r in caplog.records)
