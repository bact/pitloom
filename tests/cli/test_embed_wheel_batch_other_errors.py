# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Only a ``ValueError`` or an ``OSError`` from one wheel's embed is that
wheel's failure; any other exception is a bug and aborts the batch.

See also: :mod:`tests.cli.test_embed_wheel_batch_internal_error`
(``InternalError``, a ``ValueError`` that escapes too).
"""

from __future__ import annotations

import argparse
import types
from pathlib import Path
from typing import Any

import pytest

from pitloom.cli.commands import _embed_wheel_batch

_WHEEL = Path("demo-1.0-py3-none-any.whl")


def _try_embed(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> Any:
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


@pytest.mark.parametrize(
    "error",
    [RuntimeError("bug"), KeyError("k"), TypeError("t"), AttributeError("a")],
    ids=["runtime", "key", "type", "attribute"],
)
def test_any_other_exception_aborts_the_batch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    with pytest.raises(type(error)):
        _try_embed(monkeypatch, error)
    assert "ERROR:" not in capsys.readouterr().err  # not said as a wheel's failure


@pytest.mark.parametrize("error", [ValueError("x"), OSError("x")], ids=["value", "os"])
def test_a_value_or_os_error_is_said_for_the_wheel_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    assert _try_embed(monkeypatch, error) is None
    lines = [ln for ln in capsys.readouterr().err.splitlines() if "ERROR:" in ln]
    assert len(lines) == 1
