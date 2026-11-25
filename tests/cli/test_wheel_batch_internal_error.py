# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A programming error in one wheel's check is not that wheel's failure: in a
batch of several wheels of ``verify-wheel``, ``validate-wheel`` or
``embed-wheel`` (its embed, or its ``--verify``/``--validate`` check of the
wheel written) it reaches the top handler as one ``ERROR:`` line and the
next wheel is not processed (the per-wheel counterpart of
:mod:`tests.cli.test_embed_wheel_batch_internal_error`, through the CLI).

See also: :func:`pitloom.cli.commands.utils.report_wheel_failure`.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.cli.commands import _embed_wheel_batch, utils, verify_wheel
from pitloom.core.internal_error import InternalError
from tests.assemble.conftest import _make_dummy_wheel

pytestmark = pytest.mark.platform

_MISUSE = "kind must be 'wheel', got 'x'"
#: By case: the command line after the wheels, and the per-wheel callee that
#: raises. ``embed-wheel --verify/--validate`` embeds for real, then its check
#: of the written wheel raises (``_locate_embedded_sbom_or_report``).
_COMMANDS = {
    "verify-wheel": (["verify-wheel"], utils, "find_embedded_sbom"),
    "validate-wheel": (["validate-wheel"], utils, "find_embedded_sbom"),
    "verify-wheel-metadata": (
        ["verify-wheel"],
        verify_wheel,
        "read_wheel_name_version_from_path",
    ),
    "embed-wheel": (["embed-wheel"], _embed_wheel_batch, "embed_wheel_sbom"),
    "embed-wheel-verify": (["embed-wheel", "--verify"], utils, "find_embedded_sbom"),
    "embed-wheel-validate": (
        ["embed-wheel", "--validate"],
        utils,
        "find_embedded_sbom",
    ),
}


@pytest.mark.parametrize("command", _COMMANDS, ids=_COMMANDS)
@pytest.mark.uncoded_output(r"^ERROR: loom [a-z-]+: kind must be 'wheel', got 'x'$")
def test_internal_error_aborts_the_batch_at_the_first_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    first = _make_dummy_wheel(tmp_path / "a", "first", "1.0.0")
    second = _make_dummy_wheel(tmp_path / "b", "second", "1.0.0")
    second_bytes = second.read_bytes()
    seen: list[str] = []

    def misuse(wheel: Path, *_args: object, **_kwargs: object) -> object:
        seen.append(wheel.name)
        raise InternalError(_MISUSE)

    words, module, name = _COMMANDS[command]
    monkeypatch.setattr(module, name, misuse)
    monkeypatch.chdir(tmp_path)
    if command.endswith("-metadata"):
        monkeypatch.setattr(
            verify_wheel, "_locate_and_detect", lambda *_: (object(), "spdx3-jsonld")
        )
        monkeypatch.setattr(verify_wheel, "_check_location", lambda *_: True)
    monkeypatch.setattr(sys, "argv", ["loom", *words, str(first), str(second)])

    assert __main__.main() == 1

    err = [x for x in capsys.readouterr().err.splitlines() if x.startswith("ERROR: ")]
    assert seen == [first.name]
    assert err == [f"ERROR: loom {words[0]}: {_MISUSE}"]
    # the batch stopped: the second wheel is untouched, with no SBOM in it
    assert second.read_bytes() == second_bytes
    with zipfile.ZipFile(second) as archive:
        assert not [n for n in archive.namelist() if "/sboms/" in n]
