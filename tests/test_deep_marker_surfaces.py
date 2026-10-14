# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A requirement nesting 900 parentheses on every route: ``pyproject.toml``
``dependencies`` and ``optional-dependencies``, ``setup.cfg``
``install_requires`` and ``extras_require`` (an ``extra:marker`` key too),
an sdist's ``PKG-INFO``, a wheel's ``Requires-Dist``, a ``requirements.txt``
and a ``pylock.toml`` marker.

``packaging`` raised ``RecursionError`` parsing it, failing the whole run.
Each route now finishes, the requirement refused with the marker-nesting
cap's ``WARNING:``, the other requirements kept.

See also: tests/core/test_pep508.py (the cap, the ``RecursionError``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from tests._author_routes import CREATED, isolate, write_wheel
from tests._bounded import run_bounded
from tests._deep_marker import DEEP_REQUIREMENT
from tests.assemble.conftest import _make_sdist

_DEEP = DEEP_REQUIREMENT
_DEEP_MARKER = _DEEP.partition("; ")[2]
_HEAD = '[project]\nname = "demo"\nversion = "1.0"\n'
_CAP = "larger than the 64-level marker-nesting cap"
_META = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n"
_REQUIRES_DIST = (
    f"Requires-Dist: alpha\nRequires-Dist: {_DEEP}\n"
    f'Requires-Dist: {_DEEP} and extra == "x"\n'
)


def _project(files: dict[str, str]) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
        for name, text in files.items():
            (tmp_path / name).write_text(text, encoding="utf-8")
        return generate_project_sbom(tmp_path, creation_metadata=CREATED, offline=True)

    return run


def _sdist(tmp_path: Path) -> str:
    members: dict[str, bytes | None] = {
        "PKG-INFO": (_META + _REQUIRES_DIST).encode(),
        "pyproject.toml": None,
    }
    return generate_project_sbom(
        _make_sdist(tmp_path, members=members), creation_metadata=CREATED, offline=True
    )


def _wheel(tmp_path: Path) -> str:
    wheel = write_wheel(tmp_path, _META + _REQUIRES_DIST)
    return generate_wheel_sbom(wheel, creation_metadata=CREATED)


_ROUTES = {
    "pyproject-dependencies": _project(
        {"pyproject.toml": f"{_HEAD}dependencies = ['{_DEEP}', 'alpha']\n"}
    ),
    "pyproject-extra": _project(
        {
            "pyproject.toml": f"{_HEAD}dependencies = ['alpha']\n"
            f"[project.optional-dependencies]\nx = ['{_DEEP}']\n"
        }
    ),
    "setup-cfg": _project(
        {
            "setup.cfg": "[metadata]\nname = demo\nversion = 1.0\n[options]\n"
            f"install_requires =\n    alpha\n    {_DEEP}\n"
            f"[options.extras_require]\nx =\n    {_DEEP}\n"
            f"y:os_name == 'a' =\n    {_DEEP}\n",
            "setup.py": "from setuptools import setup\nsetup()\n",
        }
    ),
    "sdist-pkg-info": _sdist,
    "wheel-requires-dist": _wheel,
    "requirements-txt": _project(
        {
            "pyproject.toml": f"{_HEAD}dependencies = ['alpha']\n",
            "requirements.txt": f"alpha==1.0\n{_DEEP}\n",
        }
    ),
    "pylock": _project(
        {
            "pyproject.toml": f"{_HEAD}dependencies = ['alpha']\n",
            "pylock.toml": 'lock-version = "1.0"\ncreated-by = "x"\n'
            '[[packages]]\nname = "alpha"\nversion = "1.0"\n'
            f"marker = '{_DEEP_MARKER}'\n",
        }
    ),
}


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_a_deep_requirement_warns_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: str,
) -> None:
    """The run finishes: the requirement refused with the cap's
    ``WARNING:``, ``alpha`` still a dependency, nothing logged as an
    error."""
    isolate(tmp_path, monkeypatch)
    with caplog.at_level(logging.WARNING):
        sbom = run_bounded(lambda: _ROUTES[route](tmp_path))
    assert any(_CAP in message for message in caplog.messages)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    names = {e.get("name") for e in json.loads(sbom)["@graph"]}
    assert "alpha" in names
