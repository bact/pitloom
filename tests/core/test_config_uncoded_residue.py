# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An uncoded ``ValueError`` from the ``[tool.pitloom]`` reader is a bug.

Every key of the drift table, read with a wrong type, a NUL, an overlong
integer and an empty value, raises a coded error (probe of 2026-11-19: 962
cases, none uncoded). What is left is a programming error on both routes
that read a config file, the directory route
(:func:`pitloom.core.config_cascade.load_config_file`) and the sdist route
(:func:`pitloom.extract.project.sdist.read_sdist`): an
:class:`pitloom.core.internal_error.InternalError` naming the file and the
exception type, never the exception's text (a value may hold a credential).

See also: ``tests/core/test_config_load_file.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.core.config_cascade import load_config_file
from pitloom.core.internal_error import InternalError
from pitloom.extract.project.sdist import read_sdist
from tests.assemble.conftest import _make_sdist

pytestmark = pytest.mark.platform

_SECRET = "https://user:hunter2@example.org/"
_CONFIG = '[tool.pitloom]\ncreator = "x"\n'


def _uncoded(*_args: Any, **_kwargs: Any) -> None:
    raise ValueError(f"bad value {_SECRET}")


def test_the_directory_route_raises_an_internal_error(tmp_path: Path) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_text(_CONFIG, encoding="utf-8")
    with patch("pitloom.core.config_cascade.parse_pitloom_config", _uncoded):
        with pytest.raises(InternalError) as raised:
            load_config_file(config)
    text = str(raised.value)
    assert "uncoded ValueError" in text and "pyproject.toml" in text
    assert "hunter2" not in text
    # nothing chained: a traceback prints __context__ raw
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


@pytest.mark.parametrize("fmt", ["tar", "zip"])
def test_the_sdist_route_raises_an_internal_error(tmp_path: Path, fmt: str) -> None:
    sdist = _make_sdist(
        tmp_path,
        members={"pyproject.toml": _CONFIG.encode("utf-8")},
        fmt=fmt,
    )
    with patch("pitloom.extract.project.sdist.parse_pitloom_config", _uncoded):
        with pytest.raises(InternalError) as raised:
            read_sdist(sdist)
    text = str(raised.value)
    assert "uncoded ValueError" in text and "pyproject.toml" in text
    assert "hunter2" not in text
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
