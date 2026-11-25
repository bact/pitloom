# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A programming error in one wheel's embed is not a per-wheel failure.

See also: :mod:`tests.messages.test_file_unreadable_wheel` (the per-wheel
``ValueError``/``OSError`` case this one is the counterpart of).
"""

from __future__ import annotations

import argparse
import types
from pathlib import Path
from typing import Any

import pytest

from pitloom.cli.commands import _embed_wheel_batch
from pitloom.core.internal_error import InternalError

_WHEEL = Path("demo-1.0-py3-none-any.whl")


def _try_embed(monkeypatch: pytest.MonkeyPatch, error: Exception) -> Any:
    def embed(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(_embed_wheel_batch, "embed_wheel_sbom", embed)
    batch: Any = types.SimpleNamespace(
        project_dir=None,
        pitloom_config=None,
        creation_metadata=None,
        id_registry=None,
        overrides=None,
        file_cache=None,
    )
    args = argparse.Namespace(
        sbom=None,
        sbom_basename=None,
        allow_mismatch=False,
        allow_signed_wheel=False,
    )
    return _embed_wheel_batch.try_embed_one_wheel(_WHEEL, None, batch, args)


def test_internal_error_aborts_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """``InternalError`` is a ``ValueError`` but escapes the per-wheel catch."""
    with pytest.raises(InternalError):
        _try_embed(monkeypatch, InternalError("misuse"))


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ValueError("x"), marks=pytest.mark.uncoded_output(r"^ERROR: x$")),
        OSError("x"),
    ],
    ids=["value", "os"],
)
def test_other_failures_stay_per_wheel(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """A plain ``ValueError``/``OSError`` is reported and the batch goes on."""
    assert _try_embed(monkeypatch, error) is None
