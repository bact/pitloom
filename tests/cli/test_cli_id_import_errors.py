# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`loom id import` and `loom id generate` failures name the path as the user
typed it: every coded error the SBOM read raises names the SBOM itself (so
the command line adds no lead), an uncoded one keeps the lead, and a missing
SBOM or project directory is named as given, not resolved.

See also: tests/cli/test_cli_id.py (the commands end to end).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.id_registry import IdRegistry
from pitloom.messages import Message, trusted_message
from pitloom.messages.files import FILE_UNREADABLE, JSON_MALFORMED
from pitloom.messages.targets import INPUT_NOT_FOUND, SBOM_INVALID
from tests._message_drift import raised_as
from tests._unreadable import POSIX_NON_ROOT

pytestmark = pytest.mark.platform

_NS = "https://example.org/ns"


def _errors(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> list[str]:
    monkeypatch.setattr(sys, "argv", ["loom", "id", *argv])
    assert __main__.main() == 1
    return [ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("E")]


@pytest.mark.parametrize(
    ("content", "text", "entry"),
    [
        (b"nope", "not valid JSON for the SBOM; Expecting value", JSON_MALFORMED),
        (b"[1]", "not a JSON object for the SBOM", JSON_MALFORMED),
        (b'{"@graph": {}}', "SBOM @graph is not a list", SBOM_INVALID),
        (b'{"@graph": [1]}', "SBOM @graph holds an element", SBOM_INVALID),
    ],
    ids=["not-json", "not-object", "graph-not-list", "graph-element"],
)
def test_a_coded_import_error_names_the_sbom_as_typed(
    content: bytes,
    text: str,
    entry: Message,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sbom.json").write_bytes(content)
    (line,) = _errors(
        ["import", "sbom.json", "--id-registry", "r.json"], monkeypatch, capsys
    )
    assert line.startswith(f"ERROR: loom id import: FILE=sbom.json: {text}")
    assert trusted_message(line) is entry


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX, non-root")
def test_an_unreadable_sbom_is_named_as_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    sbom = tmp_path / "sbom.json"
    sbom.write_bytes(b"{}")
    sbom.chmod(0)
    try:
        (line,) = _errors(
            ["import", "sbom.json", "--id-registry", "r.json"], monkeypatch, capsys
        )
    finally:
        sbom.chmod(0o644)
    assert line == (
        "ERROR: loom id import: FILE=sbom.json: could not read for the SBOM; "
        "Permission denied [file-unreadable]"
    )
    assert trusted_message(line) is FILE_UNREADABLE


def test_an_uncoded_import_error_keeps_the_lead(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sbom.json").write_bytes(b"{}")
    (line,) = _errors(
        ["import", "sbom.json", "--id-registry", "r.json"], monkeypatch, capsys
    )
    assert line.startswith("ERROR: loom id import: failed to import SBOM 'sbom.json': ")


@pytest.mark.parametrize(
    ("argv", "text"),
    [
        (["import", "gone.json"], "SBOM file not found: 'gone.json'"),
        (
            ["import", "sbom.json", "--project-dir", "gone"],
            "project directory not found: 'gone'",
        ),
        (
            ["generate", "--project-dir", "gone", "-o", "r.json"],
            "project directory not found: 'gone'",
        ),
    ],
    ids=["import-sbom", "import-project", "generate-project"],
)
def test_a_missing_path_is_named_as_typed(
    argv: list[str],
    text: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sbom.json").write_bytes(b"{}")
    command = f"id {argv[0]}"
    lines = _errors(argv, monkeypatch, capsys)
    assert lines == [f"ERROR: loom {command}: {text} [input-not-found]"]


def test_the_library_import_of_a_missing_sbom_is_coded(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as caught:
        IdRegistry(namespace=_NS).import_sbom(tmp_path / "gone.json")
    assert raised_as(caught.value, INPUT_NOT_FOUND)
