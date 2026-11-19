# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries of the uncoded-ValueError residues found by mutation testing.

See also: ``tests/core/test_config_uncoded_residue.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.config_cascade import load_config_file
from pitloom.core.internal_error import InternalError
from pitloom.core.quote_source import quote_source
from pitloom.extract.project.sdist import read_sdist
from tests.assemble.conftest import _make_sdist

pytestmark = pytest.mark.platform

_CONFIG = '[tool.pitloom]\ncreator = "x"\n'


class _OddValueError(ValueError):
    """A ``ValueError`` subclass with no code: the type is what is said."""


def _odd(*_args: Any, **_kwargs: Any) -> None:
    raise _OddValueError("bad value")


def test_the_directory_route_names_the_file_quoted_and_the_exact_type(
    tmp_path: Path,
) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text(_CONFIG, encoding="utf-8")
    with patch("pitloom.core.config_cascade.parse_pitloom_config", _odd):
        with pytest.raises(InternalError) as raised:
            load_config_file(config)
    text = str(raised.value)
    assert text.startswith(f"config file {quote_source(config)}: ")
    assert "uncoded _OddValueError" in text  # the type of the error, not a constant


@pytest.mark.parametrize("fmt", ["tar", "zip"])
@pytest.mark.parametrize(
    ("member", "target"),
    [
        ("pyproject.toml", "pitloom.extract.project.sdist.parse_pitloom_config"),
        ("setup.cfg", "pitloom.extract.project.sdist.setup_cfg_pitloom_config"),
    ],
    ids=["pyproject", "setup-cfg"],
)
def test_the_sdist_route_names_the_member_quoted_and_the_exact_type(
    tmp_path: Path, fmt: str, member: str, target: str
) -> None:
    """Both config members: ``setup.cfg``'s reader is wrapped as the
    ``pyproject.toml`` one is."""
    content = _CONFIG if member == "pyproject.toml" else "[tool:pitloom]\ncreator = x\n"
    members: dict[str, bytes | None] = {member: content.encode()}
    if member == "setup.cfg":  # a pyproject.toml that names and configures nothing
        members["pyproject.toml"] = b'[build-system]\nrequires = ["setuptools"]\n'
    sdist = _make_sdist(tmp_path, members=members, fmt=fmt)
    with patch(target, _odd):
        with pytest.raises(InternalError) as raised:
            read_sdist(sdist)
    text = str(raised.value)
    assert text.startswith(f"config file {quote_source(f'{sdist}:{member}')}: ")
    assert "uncoded _OddValueError" in text
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
