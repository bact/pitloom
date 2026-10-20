# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The main package's ``builtTime`` is an SPDX 3 DateTime: UTC, whole
seconds, written with ``Z`` -- whatever form the pinned datetime took.

A bare ``datetime.fromisoformat()`` would fail a ``Z`` value (the form the
docs show) on Python 3.10 and pass an offset such as ``+07:00`` or
fractional seconds through unconverted.

See also: :mod:`tests.test_wall_clock_sources` (raw parsing is confined to
:func:`pitloom.assemble.spdx3.creation_info.parse_iso_datetime`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.plugins.hatch import _build_creation_metadata
from tests.assemble.embed_surfaces_shared import demo_project

_EXPECTED = "2026-01-01T00:00:00Z"


def _built_time(sbom_json: str) -> str:
    graph = json.loads(sbom_json)["@graph"]
    (built,) = [o["builtTime"] for o in graph if "builtTime" in o]
    return str(built)


@pytest.mark.parametrize(
    "pinned",
    [
        "2026-01-01T00:00:00Z",
        "2026-01-01T07:00:00+07:00",
        "2025-12-31T19:00:00-05:00",
        "2026-01-01T00:00:00",  # naive: UTC
        "2026-01-01T00:00:00.987654Z",
        "2026-01-01T00:00:00+00:00",
    ],
)
def test_built_time_is_utc_whole_seconds_with_z(pinned: str, tmp_path: Path) -> None:
    sbom = generate_project_sbom(
        demo_project(tmp_path),
        creation_metadata=CreationMetadata(build_datetime=pinned),
        offline=True,
    )
    assert _built_time(sbom) == _EXPECTED


def test_hook_pinned_datetime_reaches_built_time_as_z(tmp_path: Path) -> None:
    """The Hatchling hook passes the config's ``creation-datetime`` through
    as given; the one shared parse normalises it."""
    creation = _build_creation_metadata(
        PitloomConfig(creation_datetime="2026-01-01T07:00:00+07:00")
    )
    sbom = generate_project_sbom(
        demo_project(tmp_path), creation_metadata=creation, offline=True
    )
    assert _built_time(sbom) == _EXPECTED


def test_invalid_built_time_names_the_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid ISO 8601 datetime: yesterday"):
        generate_project_sbom(
            demo_project(tmp_path),
            creation_metadata=CreationMetadata(build_datetime="yesterday"),
            offline=True,
        )
