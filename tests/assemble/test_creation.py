# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.core.creation."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata, resolve_source_date_epoch
from tests.assemble.conftest import _make_dummy_wheel


def test_resolve_source_date_epoch_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert resolve_source_date_epoch() is None


def test_resolve_source_date_epoch_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert resolve_source_date_epoch() == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("not-a-number", "is not an integer"),
        ("1.5", "is not an integer"),
        ("0x10", "is not an integer"),
        ("99999999999999999", "is out of range"),
        ("99999999999999999999999999999999999", "is out of range"),
    ],
    ids=["text", "float", "hex", "range", "huge"],
)
def test_resolve_source_date_epoch_invalid_raises(
    monkeypatch: pytest.MonkeyPatch, raw: str, reason: str
) -> None:
    """A malformed value fails (reproducible-builds.org: a build SHOULD),
    naming the variable and the value, rather than being ignored."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", raw)
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH") as info:
        resolve_source_date_epoch()
    assert repr(raw) in str(info.value) and reason in str(info.value)


def test_resolve_source_date_epoch_empty_string_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "")
    assert resolve_source_date_epoch() is None


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo_pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    return root


def _safetensors(path: Path) -> Path:
    header = b'{"w":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}'
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\0" * 4)
    return path


_PIN = ["--creation-datetime", "2026-01-01T00:00:00Z"]
_EPOCH_ERROR = (
    "SOURCE_DATE_EPOCH='abc' is not an integer number of seconds since the Unix epoch"
)


@pytest.mark.parametrize("pinned", [False, True], ids=["unpinned", "pinned-date"])
@pytest.mark.parametrize(
    "command", ["project", "generate", "wheel", "embed-wheel", "env", "model", "enrich"]
)
def test_a_malformed_epoch_fails_every_cli_command_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    pinned: bool,
) -> None:
    """With or without a pinned creation date: one ``ERROR:`` line, exit 1,
    nothing written."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "abc")
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo_pkg", "1.0.0")
    out = tmp_path / "o.json"
    targets = {
        "project": [str(_project(tmp_path / "p")), "-o", str(out)],
        "generate": [str(_project(tmp_path / "g")), "-o", str(out)],
        "wheel": [str(wheel), "-o", str(out)],
        "embed-wheel": [str(wheel)],
        "env": ["-o", str(out)],
        "model": [str(_safetensors(tmp_path / "m.safetensors")), "-o", str(out)],
        "enrich": [str(_safetensors(tmp_path / "e.safetensors")), "-o", str(out)],
    }
    argv = ["loom", command, *targets[command], *(_PIN if pinned else [])]
    monkeypatch.setattr("sys.argv", argv)
    assert __main__.main() == 1
    err = capsys.readouterr().err.splitlines()
    lines = [ln for ln in err if "SOURCE_DATE_EPOCH" in ln]
    assert len(lines) == 1
    assert lines[0].startswith("ERROR: ") and _EPOCH_ERROR in lines[0]
    assert not out.exists()


def test_a_malformed_epoch_fails_merge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fragments = tmp_path / "frags"
    fragments.mkdir()
    monkeypatch.setattr(
        "sys.argv",
        [
            "loom",
            "project",
            str(_project(tmp_path / "p")),
            "-o",
            str(fragments / "a.json"),
        ],
    )
    assert __main__.main() == 0
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "abc")
    monkeypatch.setattr(
        "sys.argv", ["loom", "merge", str(fragments), "-o", str(tmp_path / "m.json")]
    )
    assert __main__.main() == 1
    assert _EPOCH_ERROR in capsys.readouterr().err


@pytest.mark.parametrize("pinned", [False, True], ids=["unpinned", "pinned-date"])
def test_a_malformed_epoch_fails_the_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pinned: bool
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "abc")
    metadata = CreationMetadata(
        creation_datetime="2026-01-01T00:00:00Z" if pinned else None
    )
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH='abc'"):
        generate_project_sbom(_project(tmp_path / "p"), creation_metadata=metadata)
