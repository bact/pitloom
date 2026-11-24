# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The catch-all of :func:`pitloom.extract.dataset.croissant.read_croissant`:
an unexpected exception becomes an
:class:`~pitloom.core.internal_error.InternalError` that names its type only.

See also: tests/extract/dataset/test_croissant.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.extract.dataset import croissant


def test_an_unexpected_exception_is_an_internal_error_naming_its_type_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exception's text may quote the document: it stays out of the
    message, but the exception is still the ``__cause__`` for a traceback."""
    path = tmp_path / "c.json"
    path.write_text('{"name": "x"}', encoding="utf-8")
    boom = KeyError("secret-document-text")

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise boom

    monkeypatch.setattr(croissant, "_metadata", _raise)
    with pytest.raises(InternalError) as raised:
        croissant.read_croissant(path)
    assert isinstance(raised.value, ValueError)
    assert "KeyError" in str(raised.value)
    assert "secret-document-text" not in str(raised.value)
    assert raised.value.__cause__ is boom
