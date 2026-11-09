# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""``loom model``, ``loom project`` and ``loom generate`` refuse a remote
address Pitloom cannot fetch (ssh, scp-style, file) alike, through one rule
(:func:`pitloom.extract.remote.git_url.is_unfetchable_remote`); a local path
named like one is still read.

See also: tests/cli/test_cli_model.py and tests/extract/remote/test_git_url.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from pitloom.__main__ import main
from pitloom.extract.remote.git_url import is_unfetchable_remote

_ADDRESSES = ["ssh://github.com/o/r.git", "git@github.com:o/r.git", "file:///x/y.onnx"]
_COMMANDS = ["model", "project", "generate"]


def _run(
    command: str,
    target: str,
    out: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["loom", command, target, "-o", str(out)])
    return main(), capsys.readouterr().err


@pytest.mark.parametrize("address", _ADDRESSES)
def test_the_three_commands_refuse_an_unfetchable_address_alike(
    address: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = {
        c: _run(c, address, tmp_path / "o.json", capsys, monkeypatch) for c in _COMMANDS
    }
    for command, (code, err) in results.items():
        assert code == 1, command
        assert "only http and https URLs are fetched" in err, command
        assert "not found" not in err, command
    # The same `Cannot fetch <address>: ...` text, whatever the command.
    texts = {
        err.splitlines()[-1].split("Cannot fetch ", 1)[1] for _, err in results.values()
    }
    assert len(texts) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="a name with ':' or '/'")
def test_a_local_file_named_like_an_address_is_still_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "git@github.com:o.gguf"
    (tmp_path / name).write_bytes(b"not a model")
    monkeypatch.chdir(tmp_path)
    assert os.path.exists(name) and not is_unfetchable_remote(name)
    _code, err = _run("model", name, tmp_path / "o.json", capsys, monkeypatch)
    assert "Cannot fetch" not in err


def test_a_hugging_face_id_is_no_unfetchable_address() -> None:
    assert not is_unfetchable_remote("mistralai/Mistral-7B-v0.1")
