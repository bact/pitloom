# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: build a real wheel and verify the SBOM is inside it."""

# pytest fixtures intentionally shadow the outer-scope fixture name in test params.
# pylint: disable=redefined-outer-name

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

# Skip the entire module if hatchling is not installed.
pytest.importorskip(
    "hatchling", reason="hatchling is required for wheel integration tests"
)

# Guard import after importorskip.
# pylint: disable=wrong-import-position
from hatchling.builders.wheel import WheelBuilder  # noqa: E402

# pylint: enable=wrong-import-position

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sampleproject"


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a wheel from the sampleproject fixture and return its path.

    Uses ``WheelBuilder`` directly (no subprocess, no network) so the locally
    installed Loom is picked up.  Skipped when the fixture is absent.
    """
    if not FIXTURE_DIR.exists():
        pytest.skip("sampleproject fixture not found")

    out_dir = tmp_path_factory.mktemp("wheel_out")
    builder = WheelBuilder(str(FIXTURE_DIR))
    wheel_filename = next(builder.build(directory=str(out_dir), versions=["standard"]))
    wheel_path = Path(wheel_filename)
    assert wheel_path.exists(), f"Expected wheel at {wheel_path}"
    return wheel_path


# ---------------------------------------------------------------------------
# Wheel structure — SBOM placement (PEP 770)
# ---------------------------------------------------------------------------


def test_sbom_present_in_wheel(built_wheel: Path) -> None:
    """The wheel must contain exactly one file inside .dist-info/sboms/."""
    with zipfile.ZipFile(built_wheel) as zf:
        sbom_entries = [n for n in zf.namelist() if "/sboms/" in n]
    assert len(sbom_entries) == 1, f"Expected 1 SBOM entry, found: {sbom_entries}"


def test_sbom_path_matches_pep770(built_wheel: Path) -> None:
    """The SBOM must live at <dist-info>/sboms/<basename> (PEP 770)."""
    with zipfile.ZipFile(built_wheel) as zf:
        sbom_entries = [n for n in zf.namelist() if "/sboms/" in n]
    assert len(sbom_entries) == 1
    entry = sbom_entries[0]
    # Path must be: <name>-<version>.dist-info/sboms/<filename>
    assert entry.endswith(".dist-info/sboms/sbom.spdx3.json"), (
        f"Unexpected SBOM path in wheel: {entry}"
    )


def test_sbom_is_valid_json_ld(built_wheel: Path) -> None:
    """The SBOM file inside the wheel must be valid JSON-LD."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        raw = zf.read(sbom_entry)
    data = json.loads(raw)
    assert "@context" in data, "SBOM JSON-LD must have an @context key"
    assert "@graph" in data, "SBOM JSON-LD must have a @graph key"


def test_sbom_graph_contains_package(built_wheel: Path) -> None:
    """The SBOM graph must contain a software_Package element for sampleproject."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    pkg_names = [
        e.get("name") for e in data["@graph"] if e.get("type") == "software_Package"
    ]
    assert "sampleproject" in pkg_names, (
        f"Expected 'sampleproject' package in SBOM graph, found: {pkg_names}"
    )


def test_sbom_graph_contains_creator(built_wheel: Path) -> None:
    """The SBOM graph must contain the creator declared in the hook config."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        data = json.loads(zf.read(sbom_entry))
    # sampleproject/pyproject.toml sets creator-name = "Loom CI"
    person_names = [e.get("name") for e in data["@graph"] if e.get("type") == "Person"]
    assert "Loom CI" in person_names, (
        f"Expected creator 'Loom CI' in SBOM graph, found: {person_names}"
    )


def test_sbom_is_not_empty(built_wheel: Path) -> None:
    """The SBOM file inside the wheel must have non-trivial content."""
    with zipfile.ZipFile(built_wheel) as zf:
        (sbom_entry,) = [n for n in zf.namelist() if "/sboms/" in n]
        size = zf.getinfo(sbom_entry).file_size
    assert size > 100, f"SBOM is suspiciously small ({size} bytes)"
