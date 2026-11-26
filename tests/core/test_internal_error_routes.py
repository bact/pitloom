# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An :class:`~pitloom.core.internal_error.InternalError` raised under a
broad handler reaches the caller as it is: not a ``None`` result of a
worker thread, not a model file said to be malformed, not an "authors
unread" warning, not a redirect probe with no answer.

See also: ``tests/core/test_internal_error_reraised.py`` (the lint that
keeps every broad handler so).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom._embed_overlay import adopt_project_authors
from pitloom.assemble.spdx3.deps_pypi import _prefetch_pypi_release_infos
from pitloom.core.internal_error import InternalError
from pitloom.core.project import ProjectMetadata
from pitloom.extract.ai_model.safetensors import read_safetensors
from pitloom.extract.remote._git_redirect import _probe_within

_SAFETENSORS = (
    Path(__file__).parent.parent
    / "fixtures"
    / "aimodels"
    / "safetensors"
    / "phi-tiny-random.safetensors"
)


def _bug(*_args: Any, **_kwargs: Any) -> None:
    raise InternalError("named by its raiser")


def test_a_worker_thread_bug_is_not_a_missing_release() -> None:
    with patch("pitloom.assemble.spdx3.deps_pypi._fetch_pypi_release_info", _bug):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            _prefetch_pypi_release_infos([("a", "1")])


def test_a_reader_bug_is_not_a_malformed_model() -> None:
    pytest.importorskip("safetensors")
    with patch("pitloom.extract.ai_model.safetensors.derived_parameter_count", _bug):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            read_safetensors(_SAFETENSORS)


def test_a_project_read_bug_is_not_unread_authors(tmp_path: Path) -> None:
    with patch("pitloom._embed_overlay.read_project", _bug):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            adopt_project_authors(ProjectMetadata(name="p", version="1"), tmp_path)


def test_a_probe_thread_bug_is_not_a_missing_answer() -> None:
    with patch("pitloom.extract.remote._git_redirect._probe_once", _bug):
        with pytest.raises(InternalError, match="^named by its raiser$"):
            _probe_within("https://127.0.0.1:9/r.git/info/refs", 5.0)
