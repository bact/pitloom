# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A programming error in one wheel's check is not that wheel's failure: in a
batch of several wheels of ``verify-wheel``, ``validate-wheel`` or
``embed-wheel`` it reaches the top handler as one ``ERROR:`` line and the
next wheel is not processed (the per-wheel counterpart of
:mod:`tests.cli.test_embed_wheel_batch_internal_error`, through the CLI).

See also: :func:`pitloom.cli.commands.utils.report_wheel_failure`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import _embed_wheel_batch, utils, verify_wheel
from pitloom.core.internal_error import InternalError
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_MISUSE = "kind must be 'wheel', got 'x'"
_COMMANDS = {
    "verify-wheel": (utils, "find_embedded_sbom"),
    "validate-wheel": (utils, "find_embedded_sbom"),
    "verify-wheel-metadata": (verify_wheel, "read_wheel_name_version_from_path"),
    "embed-wheel": (_embed_wheel_batch, "embed_wheel_sbom"),
}


# TODO(stage S): the line asserted below is uncoded by design; once the
# `uncoded_output` marker is registered, mark this test with
# `@pytest.mark.uncoded_output(r"ERROR: loom [a-z-]+: kind must be")`.
@pytest.mark.parametrize("command", _COMMANDS, ids=_COMMANDS)
def test_internal_error_aborts_the_batch_at_the_first_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    first = _make_dummy_wheel(tmp_path / "a", "first", "1.0.0")
    second = _make_dummy_wheel(tmp_path / "b", "second", "1.0.0")
    seen: list[str] = []

    def misuse(wheel: Path, *_args: object, **_kwargs: object) -> object:
        seen.append(wheel.name)
        raise InternalError(_MISUSE)

    module, name = _COMMANDS[command]
    monkeypatch.setattr(module, name, misuse)
    verb = command.removesuffix("-metadata")
    if command.endswith("-metadata"):
        monkeypatch.setattr(
            verify_wheel, "_locate_and_detect", lambda *_: (object(), "spdx3-jsonld")
        )
        monkeypatch.setattr(verify_wheel, "_check_location", lambda *_: True)
    monkeypatch.setattr(sys, "argv", ["loom", verb, str(first), str(second)])

    assert __main__.main() == 1

    err = [x for x in capsys.readouterr().err.splitlines() if x.startswith("ERROR: ")]
    assert seen == [first.name]
    assert err == [f"ERROR: loom {verb}: {_MISUSE}"]
