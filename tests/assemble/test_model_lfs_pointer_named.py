# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model file named on its own that is a Git LFS pointer is refused with
the pointer's ``oid``, its stated size and ``git lfs pull``; a file that only
opens like a pointer keeps the plain reason.

See also: :mod:`tests.assemble.test_model_outcome_parity` (the other
refusals on the same surfaces).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import enrich_model, generate_model_sbom
from pitloom.core.lfs_pointer import read_lfs_pointer
from tests._lfs import lfs_pointer_bytes, pointer_fixture
from tests.warning_helpers import error_lines

_OPENING = b"version https://git-lfs.github.com/spec/v1\n"
_REAL = pointer_fixture("bert-tiny-pytorch-model.bin").read_bytes()
_PULL = "run 'git lfs pull'"
_PLAIN = "m.gguf': header is a Git LFS pointer"

#: name, bytes, text every refusal holds
_CASES = {
    "real": ("m.bin", _REAL, "content not pulled"),
    "built": ("m.gguf", lfs_pointer_bytes(b"abc"), "size 3 bytes"),
    "crlf": ("m.onnx", lfs_pointer_bytes(b"abc", eol="\r\n"), "size 3 bytes"),
}
#: bytes that open like a pointer but are not one
_LOOKALIKES = {
    "malformed": _OPENING + b"oid sha256:00\nsize 1\n",
    "long": _OPENING + b"x" * 1024,
}


def _run(surface: str, path: Path, out: Path) -> None:
    if surface == "generate_model_sbom":
        generate_model_sbom(path, output_path=out)
    else:
        enrich_model(path, output_path=out)


@pytest.mark.parametrize("case", _CASES)
@pytest.mark.parametrize("surface", ("generate_model_sbom", "enrich_model"))
def test_the_library_states_the_pointer_and_the_pull(
    case: str, surface: str, tmp_path: Path
) -> None:
    name, data, text = _CASES[case]
    path = tmp_path / name
    path.write_bytes(data)
    pointer = read_lfs_pointer(path)
    assert pointer is not None
    with pytest.raises(ValueError, match="Git LFS pointer") as caught:
        _run(surface, path, tmp_path / "out.json")
    message = str(caught.value)
    assert "\n" not in message and text in message and _PULL in message
    assert f"oid sha256:{pointer.oid}" in message
    assert f"size {pointer.size} bytes" in message
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("look", _LOOKALIKES)
@pytest.mark.parametrize("surface", ("generate_model_sbom", "enrich_model"))
def test_a_lookalike_keeps_the_plain_reason(
    look: str, surface: str, tmp_path: Path
) -> None:
    path = tmp_path / "m.gguf"
    path.write_bytes(_LOOKALIKES[look])
    with pytest.raises(ValueError) as caught:
        _run(surface, path, tmp_path / "out.json")
    message = str(caught.value)
    assert message.endswith(_PLAIN)
    assert "content not pulled" not in message and _PULL not in message


@pytest.mark.parametrize("command", ["model", "enrich", "generate"])
@pytest.mark.parametrize("case", ["real", "malformed"])
def test_the_cli_exits_1_with_one_error_line(
    command: str,
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "m.bin"
    path.write_bytes(_REAL if case == "real" else _LOOKALIKES[case])
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["loom", command, str(path), "-o", str(out)])
    assert __main__.main() == 1
    err = capsys.readouterr().err
    (line,) = error_lines(err)
    assert ("oid sha256:" in line and _PULL in line) == (case == "real")
    assert "WARNING:" not in err and not out.exists()
