# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests that the installed git builds match the ``conformance`` group's pins.

The spdx3-validate build with ``model_dir`` still reports version 0.0.7, so
pip keeps a PyPI 0.0.7 already installed; only the commit tells them apart.

See also: pyproject.toml (``[dependency-groups]``), tests/_spdx3_validate.py,
docs/g7-sbom-for-ai.md (the install line it tells a reader to run).
"""

from __future__ import annotations

import json
import re
from importlib.metadata import distribution
from pathlib import Path

import pytest

from pitloom._toml_io import load_toml_file

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
G7_PAGE = PYPROJECT.parent / "docs" / "g7-sbom-for-ai.md"
_GIT_PIN = re.compile(r"^(?P<name>[\w.-]+) @ git\+(?P<url>\S+)@(?P<sha>[0-9a-f]{40})$")


def _pins() -> dict[str, str]:
    groups = load_toml_file(PYPROJECT)["dependency-groups"]
    assert isinstance(groups, dict)
    found = (_GIT_PIN.match(s) for s in groups["conformance"] if isinstance(s, str))
    return {m["name"]: m["sha"] for m in found if m}


def test_conformance_group_pins_both_packages_by_commit() -> None:
    assert set(_pins()) == {"ntia-conformance-checker", "spdx3-validate"}


@pytest.mark.parametrize("name", ("ntia-conformance-checker", "spdx3-validate"))
def test_installed_commit_matches_pin(name: str) -> None:
    raw = distribution(name).read_text("direct_url.json")
    assert raw, f"{name} is not a direct (git) install; reinstall the group"
    vcs = json.loads(raw).get("vcs_info")
    assert vcs, f"{name} is not a git install; reinstall the group"
    commit = vcs["commit_id"]
    assert commit == _pins()[name], "reinstall with: pip install --group conformance"


def test_the_g7_page_installs_the_pinned_checker() -> None:
    """The install line the G7 page gives names the commit pyproject pins."""
    found = re.findall(
        r"ntia-conformance-checker @ git\+\S+?@([0-9a-f]{40})",
        G7_PAGE.read_text(encoding="utf-8"),
    )
    assert found, "the G7 page gives no pinned install line"
    assert set(found) == {_pins()["ntia-conformance-checker"]}
