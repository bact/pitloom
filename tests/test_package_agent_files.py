# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The agent instruction files ship in neither the sdist nor the wheel.

``CLAUDE.md`` and ``GEMINI.md`` are symlinks to ``AGENTS.md`` in Git; an
sdist that leaves them out of its exclude list carries dangling links.
Both archives are built from the real tree with Hatchling, then checked by
member name. The wheel packages ``src/pitloom`` only, so a built wheel
cannot show a missing wheel exclude: that list is checked with Hatchling's
own matcher as well, at the root and in a sub-directory.
"""

from __future__ import annotations

import json
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

pytest.importorskip("hatchling", reason="hatchling builds the archives")

# pylint: disable=wrong-import-position
from hatchling.builders.sdist import SdistBuilder  # noqa: E402
from hatchling.builders.wheel import WheelBuilder  # noqa: E402

# pylint: enable=wrong-import-position

ROOT = Path(__file__).resolve().parent.parent
AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")

pytestmark = pytest.mark.skipif(
    not (ROOT / "pyproject.toml").is_file(), reason="not a source tree"
)


@pytest.fixture(name="sdist_names", scope="module")
def _sdist_names(tmp_path_factory: pytest.TempPathFactory) -> list[str]:
    """Member names of an sdist built from this tree."""
    out = tmp_path_factory.mktemp("sdist_out")
    path = next(SdistBuilder(str(ROOT)).build(directory=str(out)))
    with tarfile.open(path) as tar:
        return tar.getnames()


@pytest.fixture(name="wheel_zip", scope="module")
def _wheel_zip(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[list[str], list[str]]:
    """Member names of a wheel built from this tree and its SBOM's strings."""
    out = tmp_path_factory.mktemp("wheel_out")
    builder = WheelBuilder(str(ROOT))
    path = next(builder.build(directory=str(out), versions=["standard"]))
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        sboms = [n for n in names if "/sboms/" in n]
        strings = _strings(json.loads(zf.read(sboms[0]))) if sboms else []
    return names, strings


def _strings(node: Any) -> list[str]:
    """Return every string in a parsed JSON document."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, list):
        return [s for v in node for s in _strings(v)]
    return []


def _agent_members(names: list[str]) -> list[str]:
    return [n for n in names if PurePosixPath(n).name in AGENT_FILES]


def test_sdist_has_no_agent_files(sdist_names: list[str]) -> None:
    """No agent file, link or copy is an sdist member."""
    assert any(n.endswith("/pyproject.toml") for n in sdist_names)
    assert _agent_members(sdist_names) == []


def test_wheel_and_its_sbom_have_no_agent_files(
    wheel_zip: tuple[list[str], list[str]],
) -> None:
    """No agent file is a wheel member, nor a file of the wheel's SBOM."""
    names, sbom_strings = wheel_zip
    assert any(n.startswith("pitloom/") for n in names)
    assert sbom_strings, "the wheel carries no SBOM to read"
    assert _agent_members(names) == []
    assert _agent_members(sbom_strings) == []


@pytest.mark.parametrize("target", [SdistBuilder, WheelBuilder], ids=["sdist", "wheel"])
@pytest.mark.parametrize("name", AGENT_FILES)
@pytest.mark.parametrize("folder", ["", "docs/"], ids=["root", "nested"])
def test_target_excludes_agent_file(
    target: type[SdistBuilder] | type[WheelBuilder], name: str, folder: str
) -> None:
    """Each target's exclude list names each agent file, at any depth."""
    assert target(str(ROOT)).config.path_is_excluded(folder + name)
