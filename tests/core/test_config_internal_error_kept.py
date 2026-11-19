# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An ``InternalError`` from the settings reader is not re-wrapped.

An ``InternalError`` is a ``ValueError``, but already a bug report naming its
own cause: the directory and sdist routes let it through as it is, where an
uncoded plain ``ValueError`` becomes one that names only the file and the
exception type.

See also: ``tests/core/test_config_uncoded_residue.py``.
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

_CONFIG = b'[tool.pitloom]\ncreator = "x"\n'


def _internal(*_args: Any, **_kwargs: Any) -> None:
    raise InternalError("named by its raiser")


def test_the_directory_route_keeps_an_internal_error_as_it_is(
    tmp_path: Path,
) -> None:
    config = tmp_path / "pyproject.toml"
    config.write_bytes(_CONFIG)
    with patch("pitloom.core.config_cascade.parse_pitloom_config", _internal):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            load_config_file(config)


def test_the_sdist_route_keeps_an_internal_error_as_it_is(tmp_path: Path) -> None:
    sdist = _make_sdist(tmp_path, members={"pyproject.toml": _CONFIG}, fmt="tar")
    with patch("pitloom.extract.project.sdist.parse_pitloom_config", _internal):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            read_sdist(sdist)
