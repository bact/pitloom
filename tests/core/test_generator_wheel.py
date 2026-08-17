# ruff: noqa: F403, F405
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import (
    generate_wheel_sbom,
)

from .conftest import *


def test_generate_wheel_sbom_from_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_wheel_sbom() wires read_wheel()'s extracted metadata into
    a valid SPDX 3 JSON-LD document with the expected package name/version."""
    monkeypatch.chdir(tmp_path)
    wheel_path = _make_wheel(tmp_path, "analyzed-pkg", "2.3.4")

    sbom_json = generate_wheel_sbom(wheel_path)
    data = json.loads(sbom_json)

    assert "@graph" in data
    graph = data["@graph"]
    packages = [e for e in graph if e.get("type") == "software_Package"]
    main_package = next(p for p in packages if p["name"] == "analyzed-pkg")
    assert main_package["software_packageVersion"] == "2.3.4"
