# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading a registry file: the version checked first, every string the
file holds checked for a lone surrogate, and the shared capped reader (a
cap, a FIFO).

See also: test_registry_format_load.py (every other load failure),
tests/messages/test_registry_file.py (how the file is named).
"""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

import pitloom.core.given_file as given_file_mod
from pitloom import __main__
from pitloom.id_registry import FILE_TYPE, IdRegistry
from pitloom.messages import code_of
from tests.id_registry.shared import valid_registry_data

pytestmark = pytest.mark.platform

_LONE = "\ud800"


def _write(path: Path, data: dict[str, Any]) -> Path:
    # json.dumps writes a lone surrogate as the escape \ud800, which loads back.
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _with(**changes: Any) -> dict[str, Any]:
    data = valid_registry_data()
    data.update(changes)
    return data


def _lone_sha256() -> dict[str, Any]:
    data = valid_registry_data()
    data["elements"][FILE_TYPE]["src/a.py"]["sha256"] = _LONE
    return data


@pytest.mark.parametrize(
    ("data", "condition"),
    [
        (_with(project_root=_LONE), "project_root '\\ud800' cannot be encoded"),
        (_lone_sha256(), "sha256 '\\ud800' cannot be encoded"),
        (_with(namespace=f"https://e.org/{_LONE}"), "'namespace': namespace "),
        (_with(id_counters={_LONE: 1}), "'id_counters' key '\\ud800' is not"),
    ],
    ids=["project-root", "sha256", "namespace", "counter-key"],
)
def test_a_lone_surrogate_anywhere_is_malformed_on_read(
    tmp_path: Path, data: dict[str, Any], condition: str
) -> None:
    """Refused on read, coded, never a crash in realpath() or a failed save."""
    path = _write(tmp_path / "r.json", data)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    assert str(caught.value).startswith(f"ID registry: FILE={path}: {condition}")
    assert code_of(caught.value) == "registry-malformed"


def test_id_generate_says_a_lone_surrogate_root_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write(tmp_path / "r.json", _with(project_root=_LONE))
    before = path.read_bytes()
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", "id", "generate", "-o", str(path)])

    assert __main__.main() == 1

    (error,) = capsys.readouterr().err.splitlines()
    assert error.startswith(f"ERROR: loom id generate: ID registry: FILE={path}: ")
    assert error.endswith(" [registry-malformed]")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("data", "version"),
    [
        ({"version": 5, "namespace": "not an iri"}, "5"),
        ({"version": 5}, "5"),
        ({}, "None"),
        ({**valid_registry_data(), "version": 3, "namespace": "urn:x y"}, "3"),
        ({**valid_registry_data(), "version": "4"}, "'4'"),
    ],
    ids=["newer-bad-namespace", "newer-no-namespace", "empty", "older", "text"],
)
def test_the_version_is_checked_before_the_namespace(
    tmp_path: Path, data: dict[str, Any], version: str
) -> None:
    path = _write(tmp_path / "r.json", data)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    assert str(caught.value).startswith(
        f"ID registry: FILE={path}: version {version}, expected 4 "
    )
    assert code_of(caught.value) == "registry-wrong-format"


def test_a_registry_over_the_cap_is_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "r.json", valid_registry_data())
    monkeypatch.setattr(given_file_mod, "FETCH_MAX_BYTES", 16)

    with pytest.raises(ValueError) as caught:
        IdRegistry.load(path)

    message = str(caught.value)
    assert message.startswith(f"FILE={path}: ")
    assert message.endswith(" for the ID registry; not read")
    assert code_of(caught.value) == "over-cap"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFO on this platform")
def test_a_fifo_is_not_a_registry_and_does_not_block(tmp_path: Path) -> None:
    """Opened without waiting for a writer, refused before any read."""
    path = tmp_path / "r.json"
    os.mkfifo(path)
    caught: list[BaseException] = []

    def load() -> None:
        try:
            IdRegistry.load(path)
        except FileNotFoundError as exc:
            caught.append(exc)

    worker = threading.Thread(target=load, daemon=True)
    worker.start()
    worker.join(timeout=30)

    assert not worker.is_alive(), "the load blocked on the FIFO"
    assert len(caught) == 1
    exc = caught[0]
    assert str(exc) == f"ID registry file not found: '{path}' is not a file"
    assert code_of(exc) == "input-not-found"
