# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A URL with a thousand ``?`` in its query, planted in a project URL, is
stripped (not a ``RecursionError``) and no secret reaches the SBOM, stdout or
stderr, on every command that reads a project.

See also: tests/test_credential_surfaces.py (the planted-secret routes) and
tests/core/url_masking/test_url_masking_modes.py (the reading itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main

pytestmark = pytest.mark.platform

_DEEP = "ftp://u:S3CRET@h.invalid/x?" + "q=1?" * 1000 + "token=T0KEN"


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        "[project]\nname = 'pkg'\nversion = '0.1.0'\n"
        f"[project.urls]\nHomepage = '{_DEEP}'\n",
        encoding="utf-8",
    )
    return proj


@pytest.mark.parametrize("command", ["generate", "project"])
def test_a_deeply_nested_query_is_stripped_not_a_crash(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "o.json"
    argv = [command, str(_project(tmp_path)), "-o", str(out), "--offline"]
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert main() == 0
    seen = capsys.readouterr()
    text = out.read_text(encoding="utf-8") + seen.out + seen.err
    assert "S3CRET" not in text and "T0KEN" not in text
    assert "Traceback" not in text


def test_a_url_that_cannot_be_masked_never_prints_raw(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An error whose text the masker fails on is a fixed text, never the
    exception's own (the traceback the default hook prints holds it)."""

    def fail(*_args: object, **_kwargs: object) -> str:
        raise RecursionError

    monkeypatch.setattr("pitloom.log_masking.masked_given_path", fail)
    monkeypatch.setattr(sys, "argv", ["loom", "enrich", _DEEP, "-o", "x.json"])
    main()
    seen = capsys.readouterr()
    assert "S3CRET" not in seen.err + seen.out
