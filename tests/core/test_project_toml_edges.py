# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the project TOML loader found by mutation testing.

See also: ``tests/core/test_project_toml.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core._project_toml import load_project_toml, load_project_toml_bytes
from pitloom.messages.files import CONFIG_USE, METADATA_USE

pytestmark = pytest.mark.platform


def test_a_file_gone_since_the_check_names_the_callers_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kind comes from the caller on this route too, not a fixed word."""
    path = tmp_path / "c.toml"
    path.write_bytes(b"x = 1\n")

    def vanish(_: Path) -> dict[str, object]:
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr("pitloom.core._project_toml.load_toml_file", vanish)
    with pytest.raises(FileNotFoundError) as exc:
        load_project_toml(path, kind="config file", use=CONFIG_USE)
    assert "config file" in str(exc.value)


@pytest.mark.parametrize("use", [METADATA_USE, CONFIG_USE], ids=["metadata", "config"])
def test_member_bytes_that_are_not_utf8_name_the_given_use(use: str) -> None:
    with pytest.raises(ValueError) as exc:
        load_project_toml_bytes(b"\xff[project]\n", file="a.tar.gz:p.toml", use=use)
    assert use in str(exc.value)


@pytest.mark.parametrize("route", ["gone", "file-toml", "bytes-toml", "bytes-deep"])
def test_a_coded_error_does_not_chain_the_parser_error(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``from None``: the user reads the coded line, not a parser traceback."""
    path = tmp_path / "p.toml"
    path.write_bytes(b"a = = 1\n")

    def vanish(_: Path) -> dict[str, object]:
        raise FileNotFoundError(2, "gone")

    def raise_it() -> None:
        if route == "gone":
            monkeypatch.setattr("pitloom.core._project_toml.load_toml_file", vanish)
            load_project_toml(path, kind="pyproject.toml", use=METADATA_USE)
        elif route == "file-toml":
            load_project_toml(path, kind="pyproject.toml", use=METADATA_USE)
        elif route == "bytes-toml":
            load_project_toml_bytes(b"a = = 1\n", file="a:p", use=METADATA_USE)
        else:
            load_project_toml_bytes(
                b"x = " + b"[" * 3000 + b"]" * 3000, file="a:p", use=METADATA_USE
            )

    with pytest.raises((ValueError, FileNotFoundError)) as exc:
        raise_it()
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__
