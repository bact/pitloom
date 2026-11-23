# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SBOM fragment lines under attacker text: a fragment is untrusted
input, so a key, a value, a name, an spdxId and a configured path each may
hold a line break, an escape sequence, a workflow command, a URL credential,
a token and a fake trailing code. Each says one masked, escaped line that
keeps its own code, and a value of 10 MB prints as its excerpt.

See also: tests/messages/test_fragments.py (the entries, lines and fields)
and tests/messages/test_fragments_surfaces.py (the lines on every surface).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import FragmentMergeError
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import EXCERPT_CHARS, configure_logging
from pitloom.messages import MESSAGES, code_of, trusted_message
from pitloom.messages.fragments import (
    FRAGMENT_CONFLICT,
    FRAGMENT_MISSING,
    warn_property_conflict,
)
from tests._license_graph import fragment_graph

pytestmark = pytest.mark.platform  # an escape, a path, stderr text

_NS = "https://spdx.org/spdxdocs/frag"
_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
#: A line break, an escape, a workflow command, a URL credential, a token, a
#: fake code and the code of another message: each said in one line.
_HOSTILE = (
    "\r\n\x1b[31m::error::boom https://u:s3cret@h/ "
    f"{_TOKEN} [over-cap] [fragment-missing]"
)
_TAGS = ("ERROR: ", "WARNING: ", "INFO: ")


def _write(path: Path, *elements: dict[str, Any]) -> None:
    path.write_bytes(json.dumps(fragment_graph(list(elements))).encode("utf-8"))


def _package(spdx_id: str, **extra: Any) -> dict[str, Any]:
    return {"type": "software_Package", "spdxId": spdx_id, "name": "p", **extra}


def _run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], names: list[str]
) -> tuple[list[str], FragmentMergeError | None]:
    """The lines ``merge_fragments`` of the fragments *names* printed on
    stderr, and what it raised."""
    configure_logging()
    frags = [FragmentConfig(path=n) for n in names]
    raised: FragmentMergeError | None = None
    try:
        merge_fragments(tmp_path, frags, Spdx3JsonExporter())
    except FragmentMergeError as exc:
        raised = exc
    return capsys.readouterr().err.splitlines(), raised


def _assert_one_masked_line_each(lines: list[str], codes: list[str]) -> None:
    """*lines* are one line per record, each tagged once, masked and without
    a raw control character, and each trusted as the message of its own code."""
    assert [trusted_message(ln) for ln in lines] == [MESSAGES[c] for c in codes]
    for line in lines:
        assert line.startswith(_TAGS) and not line.partition(": ")[2].startswith(_TAGS)
        assert "s3cret" not in line and _TOKEN not in line
        assert "\x1b" not in line and "\r" not in line
        assert line.endswith(f" [{code_of_line(line)}]")


def code_of_line(line: str) -> str:
    """The code a line ends in."""
    return line.rpartition(" [")[2].removesuffix("]")


# -- a hostile fragment, through the merge --------------------------------------


def _key_conflict(tmp_path: Path) -> list[str]:
    entry = {"type": "DictionaryEntry", "key": _HOSTILE}
    for name, value in (("a.json", "1"), ("b.json", "2")):
        model = {
            "type": "ai_AIPackage",
            "spdxId": f"{_NS}#M",
            "name": "m",
            "ai_hyperparameter": [{**entry, "value": value}],
        }
        _write(tmp_path / name, model)
    return ["a.json", "b.json"]


def _value_conflict(tmp_path: Path) -> list[str]:
    for name, first in (("a.json", "A"), ("b.json", "B")):
        _write(tmp_path / name, _package(f"{_NS}#P", description=first + _HOSTILE))
    return ["a.json", "b.json"]


def _spdx_id_conflict(tmp_path: Path) -> list[str]:
    """One id on two elements of a type: the line names the id, then the new
    one the later element gets in the id's own namespace."""
    shared = f"{_NS}#P{_HOSTILE}"
    _write(tmp_path / "a.json", _package(shared))
    dataset = {
        "type": "dataset_DatasetPackage",
        "spdxId": shared,
        "name": "p",
        "dataset_datasetType": ["text"],
    }
    _write(tmp_path / "b.json", dataset)
    return ["a.json", "b.json"]


def _name_conflict(tmp_path: Path) -> list[str]:
    for n, digest in (("a.json", "a" * 64), ("b.json", "b" * 64)):
        element = {
            "type": "software_File",
            "spdxId": f"{_NS}#F-{n}",
            "name": f"f{_HOSTILE}",
            "verifiedUsing": [
                {"type": "Hash", "algorithm": "sha256", "hashValue": digest}
            ],
        }
        _write(tmp_path / n, element)
    return ["a.json", "b.json"]


def _unknown_key(tmp_path: Path) -> list[str]:
    document = {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {"type": "SoftwareAgent", "spdxId": f"{_NS}#A", "name": "n", _HOSTILE: 1}
        ],
    }
    (tmp_path / "a.json").write_bytes(json.dumps(document).encode("utf-8"))
    return ["a.json"]


def _dangling_ids(tmp_path: Path) -> list[str]:
    relation = {
        "type": "Relationship",
        "spdxId": f"{_NS}#R{_HOSTILE}",
        "from": f"{_NS}#P",
        "to": [f"{_NS}#gone{_HOSTILE}"],
        "relationshipType": "other",
    }
    _write(tmp_path / "a.json", _package(f"{_NS}#P"), relation)
    return ["a.json"]


# pylint: disable-next=unused-argument
def _path(tmp_path: Path) -> list[str]:
    """A configured path that is no file: shown as written, escaped."""
    return [f"gone{_HOSTILE}.json"]


_SCENARIOS: dict[str, tuple[Callable[[Path], list[str]], list[str]]] = {
    "key": (_key_conflict, ["fragment-conflict"]),
    "value": (_value_conflict, ["fragment-conflict"]),
    "spdx-id": (_spdx_id_conflict, ["fragment-id-conflict"]),
    "name": (_name_conflict, ["fragment-hash-conflict"]),
    "unknown-key": (_unknown_key, ["fragment-invalid"]),
    "reference": (_dangling_ids, ["reference-not-found"]),
    "path": (_path, ["input-not-found/fragment"]),
}


#: Windows refuses ``\r``, ``:`` and ``?`` in a file name (the stat then fails
#: with an error that is not "missing"), so a hostile *path* is a POSIX case;
#: the same writers say every other value there.
_POSIX = sys.platform != "win32"
_NEEDS_POSIX = pytest.mark.skipif(not _POSIX, reason="a file name Windows refuses")


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param(n, marks=_NEEDS_POSIX) if n == "path" else n
        for n in sorted(_SCENARIOS)
    ],
)
def test_attacker_text_in_a_fragment_is_one_masked_line_with_its_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], scenario: str
) -> None:
    build, codes = _SCENARIOS[scenario]
    lines, raised = _run(tmp_path, capsys, build(tmp_path))
    _assert_one_masked_line_each(lines, codes)
    if scenario == "reference":  # the ERROR is the exception's, with no value
        assert raised is not None
        assert code_of(raised) == "reference-not-found" and "\n" not in str(raised)
    for line in lines:  # the fake codes never become the line's code
        assert code_of_line(line) in codes
    assert any("ghp_***" in ln or "https://***:***@h/" in ln for ln in lines)


@_NEEDS_POSIX
@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
def test_a_hostile_configured_path_is_one_line_in_the_error_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], required: bool
) -> None:
    configure_logging()
    name = f"gone{_HOSTILE}.json"
    frag = FragmentConfig(path=name, required=required)
    raised: FragmentMergeError | None = None
    try:
        merge_fragments(tmp_path, [frag], Spdx3JsonExporter())
    except FragmentMergeError as exc:
        raised = exc
    (said,) = capsys.readouterr().err.splitlines()
    assert said.endswith("[input-not-found/fragment]")
    assert (raised is not None) is required
    if raised is not None:
        text = str(raised)
        assert code_of(raised) == FRAGMENT_MISSING.code and "\n" not in text
        assert "s3cret" not in text and _TOKEN not in text and "\x1b" not in text
        assert text.startswith("1 required SBOM fragment(s) not merged: ")
        assert trusted_message(f"ERROR: {text} [fragment-missing]") is FRAGMENT_MISSING


def test_only_the_real_code_makes_a_line_trusted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The text says ``[fragment-missing]`` and ``[over-cap]`` inside; the line
    is the message of the code it ends in, ``fragment-conflict``."""
    lines, _ = _run(tmp_path, capsys, _value_conflict(tmp_path))
    (line,) = lines
    assert line.count("[fragment-missing]") == 2  # kept and dropped
    assert not line.endswith("[fragment-missing]")
    assert trusted_message(line) is FRAGMENT_CONFLICT


# -- a value of 10 MB ----------------------------------------------------------


def test_a_10_mb_conflicting_value_prints_as_its_excerpt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    big = 10_000_000
    for name, fill in (("a.json", "a"), ("b.json", "b")):
        _write(tmp_path / name, _package(f"{_NS}#P", description=fill * big))
    lines, _ = _run(tmp_path, capsys, ["a.json", "b.json"])
    (line,) = lines
    assert trusted_message(line) is FRAGMENT_CONFLICT
    # Two excerpts of at most EXCERPT_CHARS, each cut with "...", and the rest.
    assert len(line) < 2 * EXCERPT_CHARS + 200
    assert line.count("...") == 2 and "a" * (EXCERPT_CHARS + 1) not in line
    assert "a" * 100 in line and "b" * 100 in line


@pytest.mark.parametrize(
    "length", [EXCERPT_CHARS - 1, EXCERPT_CHARS, EXCERPT_CHARS + 1]
)
def test_a_value_is_cut_at_the_excerpt_limit_not_before(
    capsys: pytest.CaptureFixture[str], length: int
) -> None:
    configure_logging()
    warn_property_conflict(
        logging.getLogger("pitloom.assemble.x"),
        spdx_id=f"{_NS}#P",
        prop="description",
        kept="k" * length,
        dropped="d",
    )
    (line,) = capsys.readouterr().err.splitlines()
    assert ("..." in line) is (length > EXCERPT_CHARS)
