# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Blank space around a licence text (leading blank lines, spaces and tabs,
final line breaks) is serialisation: whatever it is,
every surface records one ``licenseText``, from the project's own file
through Hatchling's ``METADATA`` to a dependency's PyPI record.

See also: :mod:`tests.assemble.test_license_elements_classifier` (the text
kept as written) and :mod:`tests.assemble.test_license_elements_surfaces`.
"""

from __future__ import annotations

import email
import itertools
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.metadata.spec import get_core_metadata_constructors
from hatchling.plugin.manager import PluginManager

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3._license_elements import _without_blank_ends
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.creation import CreationMetadata
from pitloom.core.project import ProjectMetadata
from pitloom.extract.project.installed import _parse_installed_metadata
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import _populate_metadata_from_email
from tests._license_graph import (
    dependency_graph,
    deployed,
    graph_of,
    hook_metadata,
    onnx_model,
    project_graph,
)

from .conftest import _make_sdist

_TEXT = "Acme Licence\n  No use."  # an inner indent is text
#: The same text as a file may hold it: leading blank space and final line
#: breaks around it.
_AS_WRITTEN = [
    *(_TEXT + ending for ending in ("", "\n", "\n\n", "\r\n", "\r\n\r\n", "\r")),
    "   " + _TEXT,
    "\n\n  " + _TEXT + "\n",
    "\t" + _TEXT,
]


def _project_dir(tmp: Path, written: str) -> Path:
    """A project whose ``license = {file = ...}`` holds the text with
    *written*, byte for byte."""
    (tmp / "COPYING.txt").write_bytes(written.encode())
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\nlicense = {file = "COPYING.txt"}\n',
        encoding="utf-8",
    )
    (tmp / "demo").mkdir()
    (tmp / "demo" / "__init__.py").write_text("", encoding="utf-8")
    return tmp


def _metadata_file(tmp: Path) -> str:
    """The ``METADATA`` Hatchling writes for the project."""
    core = hatchling_metadata_core.ProjectMetadata(str(tmp), PluginManager())
    text: str = get_core_metadata_constructors()["2.4"](core)
    return text


def _built(metadata: ProjectMetadata) -> list[dict[str, Any]]:
    metadata.version = metadata.version or "1.0"
    return project_graph(metadata)


def _directory(tmp: Path) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(generate_project_sbom(tmp, offline=True))[
        "@graph"
    ]
    return graph


def _wheel(tmp: Path) -> list[dict[str, Any]]:
    metadata = ProjectMetadata(name="demo")
    _populate_metadata_from_email(
        metadata,
        metadata.provenance,
        email.message_from_string(_metadata_file(tmp)),
        "Source: wheel METADATA",
    )
    return _built(metadata)


def _sdist(tmp: Path) -> list[dict[str, Any]]:
    out = tmp / "out"
    out.mkdir()
    sdist = _make_sdist(out, members={"PKG-INFO": _metadata_file(tmp).encode()})
    return _built(read_sdist(sdist, read_config=False).metadata)


def _installed(tmp: Path) -> list[dict[str, Any]]:
    msg = email.message_from_string(_metadata_file(tmp))
    return _built(_parse_installed_metadata(msg, "Source: demo.dist-info"))


def _installed_value(tmp: Path) -> str:
    """The ``License`` value an installed copy's metadata gives, folded."""
    value = email.message_from_string(_metadata_file(tmp))["License"]
    return str(value)


def _dependency(tmp: Path, *, pypi: bool) -> list[dict[str, Any]]:
    """A dependency's installed copy (its folded METADATA value) or, not
    installed, its PyPI record (the text as uploaded)."""
    if pypi:
        raw = (tmp / "COPYING.txt").read_bytes().decode()
        return dependency_graph(None, {"license": raw})
    return dependency_graph({"License": _installed_value(tmp)}, offline=True)


def _ai_model(tmp: Path) -> list[dict[str, Any]]:
    """An AI model's own metadata stating the text as read."""
    model = onnx_model((tmp / "COPYING.txt").read_bytes().decode())
    return graph_of(build_model(model, CreationMetadata()))


_SURFACES: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
    "directory": _directory,
    "hook": lambda tmp: _built(hook_metadata(tmp)),
    "wheel": _wheel,
    "sdist": _sdist,
    "installed-project": _installed,
    "env-package": lambda tmp: graph_of(deployed({"License": _installed_value(tmp)})),
    "dependency-installed": lambda tmp: _dependency(tmp, pypi=False),
    "dependency-pypi": lambda tmp: _dependency(tmp, pypi=True),
    "ai-model": _ai_model,
}


@pytest.mark.parametrize("surface", list(_SURFACES))
@pytest.mark.parametrize("written", _AS_WRITTEN, ids=repr)
def test_blank_space_around_a_text_gives_one_text_on_every_surface(
    surface: str, written: str, tmp_path: Path
) -> None:
    graph = _SURFACES[surface](_project_dir(tmp_path, written))
    texts = [
        e["simplelicensing_licenseText"]
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
    ]
    assert texts == [_TEXT]


#: The rule as stated, independently written: leading blank lines, spaces
#: and tabs, and the final line breaks.
_RULE = re.compile(r"\A[ \t\r\n]+|(?:\r\n|\n|\r)+\Z")


def test_blank_ends_follow_the_rule_for_every_short_string() -> None:
    """Every string up to six characters over ``a``, space, tab, CR, LF."""
    for size in range(7):
        for chars in itertools.product("a \t\r\n", repeat=size):
            text = "".join(chars)
            assert _without_blank_ends(text) == _RULE.sub("", text), repr(text)


def test_a_long_run_of_inner_line_breaks_is_linear() -> None:
    """A quadratic strip took seconds on 20,000 inner line breaks; the
    bound is generous, a regression is orders of magnitude slower."""
    text = "a" + "\n" * 20_000 + "b\n"
    start = time.monotonic()
    assert _without_blank_ends(text) == text[:-1]
    assert time.monotonic() - start < 3
