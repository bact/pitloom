# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared licence value read through ``licenseid.resolve``: what Pitloom
accepts (``Apache2`` is ``Apache-2.0``), how it says so (``INFO:`` once, the
provenance keys) and what it leaves alone (a bare deprecated id, several
licences, a compound with an unreadable part, no database).

See also: tests/extract/test_license_spdx_only_fields.py (the warning for a
value nothing reads) and docs/metadata-provenance-licences.md.
"""

# pylint: disable=protected-access

from __future__ import annotations

import importlib
import json
import logging
import re
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from licenseid import DatabaseNotReadyError
from licenseid import resolve as licenseid_resolve

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract import _license, _license_resolve
from pitloom.extract._license import (
    classify_license,
    clear_resolution_cache,
    resolve_declared_value,
    tag_license_normalization,
    warn_unless_expression,
)
from tests._license_graph import license_elements

_LOGGER = "pitloom.extract._license_resolve"


def _said(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == _LOGGER and r.levelno == level
    ]


@pytest.mark.parametrize(
    ("raw", "expression", "steps"),
    [
        ("Apache2", "Apache-2.0", "separator, version_spelling"),
        ("Apache License 2.0", "Apache-2.0", "listed_name"),
        ("MIT License", "MIT", "listed_name"),
        ("CC BY 4.0", "CC-BY-4.0", "separator"),
        ("Apache 2.0,", "Apache-2.0", "separator"),  # sentence punctuation
        ("LGPL v2.1 only", "LGPL-2.1-only", "separator"),
        ("GPL 3.0 or later", "GPL-3.0-or-later", "separator, stated_qualifier"),
        ("GPL-3.0 or later", "GPL-3.0-or-later", "stated_qualifier"),
        ("Apache\u20112.0", "Apache-2.0", "separator"),  # non-breaking hyphen
        ('BSD 3-Clause "New" or "Revised" License', "BSD-3-Clause", "listed_name"),
        ("Yahoo! Public License v1.0", "YPL-1.0", "listed_name"),
    ],
    ids=[
        "apache2",
        "listed-name",
        "mit-license",
        "cc-by",
        "comma",
        "lgpl-only",
        "or-later",
        "stated",
        "unicode-hyphen",
        "list-name-quotes",
        "list-name-bang",
    ],
)
def test_a_value_the_resolver_decided_is_an_expression_said_once_at_info(
    raw: str,
    expression: str,
    steps: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reading is recorded as the expression, one ``INFO:`` per value (the
    repeats are ``DEBUG:``), and the provenance names the decision and keeps
    the value as written."""
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        results = [classify_license(raw) for _ in range(3)]
    got = results[0]
    assert results == [got] * 3
    assert got is not None
    assert (got.kind, got.value, got.raw) == ("expression", expression, raw)
    (info,) = _said(caplog, logging.INFO)
    assert info == f"LICENSE={raw!r}: read as {expression} ({steps})"
    assert len(_said(caplog, logging.DEBUG)) == 2
    note = tag_license_normalization("P", raw, expression)
    assert f"Normalized-From: {raw}" in note
    assert "Method: licenseid_resolution" in note
    assert f"Resolution-1: {raw} -> {expression} (" in note
    assert "Tool: licenseid==" in note


def test_a_plus_after_a_respelling_is_an_expansion_apart_from_it() -> None:
    note = tag_license_normalization("P", "GPLv3+", "GPL-3.0-or-later")
    assert "Resolution-1: GPLv3+ -> GPL-3.0-or-later (" in note
    assert "Expansion-1: plus_to_or_later" in note


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("GPL-2.0+", "GPL-2.0-or-later"),  # Pitloom's own rewrite of a listed id
        ("standardml-nj", "StandardML-NJ"),  # the resolver would say SMLNJ
        ("(GPL-3.0+)", "GPL-3.0-or-later"),
    ],
)
def test_a_value_pitloom_parses_itself_is_not_credited_to_licenseid(
    raw: str, normalized: str
) -> None:
    """The keys name only what ``licenseid`` read, so a value that needs no
    database has the same provenance with and without one."""
    with_db = tag_license_normalization("P", raw, normalized)
    assert "licenseid" not in with_db and "Resolution" not in with_db
    with patch("pitloom.extract._license._matcher", return_value=None):
        clear_resolution_cache()
        assert tag_license_normalization("P", raw, normalized) == with_db


def _answer(category: str) -> Any:
    """A ``licenseid`` answer of *category*, with one applied step and one
    that was declined."""
    steps = [
        {"kind": "trim", "applied": False},
        {"kind": "id_case", "applied": True},
    ]
    return {"expression": "MIT", "category": category, "steps": steps, "expansions": []}


@pytest.mark.parametrize(
    ("category", "decided"),
    [
        ("exact", False),
        ("lexical", False),
        ("plus_to_or_later", False),
        ("separator", True),
        ("deprecated_equal_successor", True),
    ],
)
def test_only_a_decision_beyond_form_is_said_at_info_and_noted(
    category: str, decided: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Case, spacing and ``+`` are the author's licence: ``DEBUG:`` and no
    ``Method``/``Resolution-1``; a declined step is not listed."""
    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER),
        patch("pitloom.extract._license.resolve", return_value=_answer(category)),
    ):
        resolved = _license_resolve.resolve_value("x")
        assert resolved is not None and resolved.decided is decided
        assert resolved.steps == ("id_case",)
        _license_resolve.say_resolved("x", resolved, None)
        note = _license_resolve.resolution_notes("x", "MIT")
    assert len(_said(caplog, logging.INFO)) == int(decided)
    assert len(_said(caplog, logging.DEBUG)) == int(not decided)
    assert ("Resolution-1: x -> MIT (id_case)" in note) is decided
    assert ("Method: licenseid_resolution" in note) is decided
    assert "Expansion" not in note


def test_a_reading_with_a_plus_outside_the_grammar_is_kept_as_the_gap_reading() -> None:
    """The answer is checked again by the strict parse, then the gap reading
    (``Apache-2.0+`` is valid SPDX the parser does not read)."""
    answer = _answer("separator") | {"expression": "Apache-2.0+"}
    with patch("pitloom.extract._license.resolve", return_value=answer):
        got = classify_license("Apache 2.0+", warn=False)
    assert got is not None and (got.kind, got.value) == ("expression", "Apache-2.0+")


def test_a_value_is_said_once_by_its_text_not_by_its_reading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        classify_license("Apache2")
        classify_license("Apache 2.0")  # the same expression, another value
    assert len(_said(caplog, logging.INFO)) == 2


def test_the_answers_are_dropped_when_the_database_is_found_unusable() -> None:
    resolve_declared_value("Apache2")
    assert _license._RESOLUTIONS
    _license._database_unusable(RuntimeError("x"))
    assert not _license._RESOLUTIONS


@pytest.mark.parametrize(
    "raw",
    [
        "BSD",  # several licences
        "GPL",
        "Apache2 OR MIT",  # a compound with a part only licenseid reads
        "Acme-Terms",  # none
        "MIT/Apache-2.0",  # not an SPDX operator
        "GPL-2.0-only+",  # malformed
        "Apache2\nLicense",  # more than one line
        "Apache\r2.0",  # a line break that is not \n
        "Apache\x0b2.0",
        "Apache\x1c2.0",
        "Apache\u20282.0",
        # a character the resolver would drop is the author's, not a spelling
        "Apache 2.0?",
        "Apache2 ***",
        "MIT License!",  # a List name plus a character
        "GPL-3.0-or-later!",
        "Apache\ufffd2.0",
        "Apache 2.0\udc80",  # a lone surrogate becomes U+FFFD
    ],
)
def test_a_value_naming_no_single_licence_stays_text(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None and got.kind == "text"
    # a lone surrogate is replaced by U+FFFD on the way in
    assert got.value == re.sub("[\ud800-\udfff]", "\ufffd", raw.strip())


@pytest.mark.parametrize("raw", ["GPL-3.0", "GPL-2.0", "LGPL-2.1"])
def test_a_bare_deprecated_id_is_never_narrowed(raw: str) -> None:
    got = classify_license(raw)
    assert got is not None
    assert (got.kind, got.value) == ("expression", raw)
    assert "-only" not in got.value and "-or-later" not in got.value


@pytest.mark.parametrize("raw", ["Apache2", "MIT License", "GPLv3+", "CC BY 4.0"])
def test_resolving_is_idempotent_and_deterministic(raw: str) -> None:
    """The result is the same every time, and reading it again changes
    nothing: it is an id the strict parse reads, with no further note."""
    first = classify_license(raw, warn=False)
    assert first is not None and first.value != raw
    assert classify_license(raw, warn=False) == first
    again = classify_license(first.value, warn=False)
    assert again is not None and again.value == first.value
    assert tag_license_normalization("P", first.value, again.value) == "P"


def test_a_spdx_only_field_says_the_reading_and_does_not_warn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        for _ in range(2):
            warn_unless_expression("Apache2", "project.license")
        warn_unless_expression("Acme2", "project.license")
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert infos == [
        "FIELD=project.license LICENSE='Apache2': read as Apache-2.0"
        " (separator, version_spelling)"
    ]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "LICENSE='Acme2'" in warnings[0]


@pytest.mark.parametrize(
    "failure",
    [DatabaseNotReadyError("missing"), RuntimeError("boom")],
    ids=["no-database", "resolver-error"],
)
def test_no_reading_when_the_resolver_cannot_answer(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """A missing database or a failing resolver leaves the value as text, as
    before; a database problem is warned once, a resolver bug is a debug."""
    with (
        caplog.at_level(logging.DEBUG, logger="pitloom"),
        patch("pitloom.extract._license.resolve", side_effect=failure),
    ):
        got = classify_license("Apache2", warn=False)
        classify_license("Apache2", warn=False)
    assert got is not None and (got.kind, got.value) == ("text", "Apache2")
    unusable = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "database cannot be used" in r.getMessage()
    ]
    assert len(unusable) == (1 if isinstance(failure, DatabaseNotReadyError) else 0)


def test_an_answer_the_strict_parse_refuses_is_not_recorded() -> None:
    """The reading is checked again: an expression Pitloom's parser does not
    read is no licence."""
    answer: Any = {
        "expression": "Not-A-Listed-Id",
        "category": "separator",
        "steps": [],
        "expansions": [],
    }
    with patch("pitloom.extract._license.resolve", return_value=answer):
        got = classify_license("Apache2", warn=False)
    assert got is not None and (got.kind, got.value) == ("text", "Apache2")


@pytest.mark.parametrize(
    "category", ["assumed_only", "deprecated_ambiguous", "expression"]
)
def test_a_category_that_decides_nothing_is_not_accepted(category: str) -> None:
    answer: Any = {
        "expression": "MIT",
        "category": category,
        "steps": [],
        "expansions": [],
    }
    with patch("pitloom.extract._license.resolve", return_value=answer):
        got = classify_license("Acme2", warn=False)
    assert got is not None and (got.kind, got.value) == ("text", "Acme2")


def _project(root: Path, value: str) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "p"\nversion = "1.0"\nlicense = {json.dumps(value)}\n',
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize("surface", ["cli", "library"])
def test_end_to_end_a_respelt_licence_is_declared_as_the_id_with_one_info(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _project(tmp_path / "p", "Apache2")
    out = tmp_path / "sbom.json"
    if surface == "cli":
        argv = ["loom", "project", str(root), "-o", str(out), "--offline"]
        monkeypatch.setattr(
            sys, "argv", [*argv, "--creation-datetime", "2026-01-01T00:00:00Z"]
        )
        assert main() == 0
    else:
        generate_project_sbom(
            root,
            output_path=out,
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    err = capsys.readouterr().err.splitlines()
    assert [line for line in err if "LICENSE='Apache2'" in line] == [
        "INFO: FIELD=project.license LICENSE='Apache2': read as Apache-2.0"
        " (separator, version_spelling)"
    ]
    sbom = json.loads(out.read_text(encoding="utf-8"))
    (element,) = license_elements(sbom["@graph"])
    assert element["simplelicensing_licenseExpression"] == "Apache-2.0"
    statements = [e.get("statement", "") for e in sbom["@graph"]]
    assert any("licenseid_resolution" in s for s in statements)


def test_the_tool_key_is_left_out_when_the_licenseid_version_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A re-spelling is still recorded; only ``Tool`` needs the version."""
    monkeypatch.setattr(_license_resolve, "_LICENSEID_VERSION", None)
    note = tag_license_normalization("P", "Apache2", "Apache-2.0")
    assert "Resolution-1: Apache2 -> Apache-2.0" in note
    assert "Tool:" not in note


def test_an_uninstalled_licenseid_distribution_gives_no_version() -> None:
    """Metadata is missing for a source checkout or a vendored copy: the
    version is ``None``, not an error at import."""
    with patch(
        "importlib.metadata.version", side_effect=PackageNotFoundError("licenseid")
    ):
        reloaded = importlib.reload(_license_resolve)
    try:
        assert reloaded._LICENSEID_VERSION is None
    finally:
        importlib.reload(_license_resolve)
    assert _license_resolve._LICENSEID_VERSION is not None


def test_a_value_is_resolved_once_and_a_failure_is_not_remembered() -> None:
    """Callers share one answer per value; a failed answer is asked again."""
    real = licenseid_resolve
    with patch("pitloom.extract._license.resolve", side_effect=real) as spy:
        for _ in range(3):
            classify_license("Apache2", warn=False)
        assert spy.call_count == 1
    with patch(
        "pitloom.extract._license.resolve", side_effect=[RuntimeError("boom"), None]
    ) as flaky:
        assert resolve_declared_value("Acme2") is None
        assert resolve_declared_value("Acme2") is None  # asked again, not cached
        assert flaky.call_count == 2


def test_the_answers_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_license, "_MAX_RESOLUTIONS", 2)
    for value in ("Acme1", "Acme2", "Acme3"):
        resolve_declared_value(value)
    assert list(_license._RESOLUTIONS) == ["Acme3"]


def test_the_answers_are_dropped_when_the_database_file_changes() -> None:
    """``licenseid update`` in a long-lived process: the next answer is asked
    of the new database, as licence text detection does."""
    with (
        patch("pitloom.extract._license.resolve", side_effect=licenseid_resolve) as spy,
        patch.object(
            _license, "_database_stamp", side_effect=[(1, 1, 1)] * 2 + [(2, 1, 1)]
        ),
    ):
        for _ in range(3):
            resolve_declared_value("Apache2")
    assert spy.call_count == 2


def test_an_answer_read_across_a_database_change_is_not_kept() -> None:
    """Another thread saw a new database while this one was resolving."""

    def resolve_during_change(*args: Any) -> Any:
        _license._RESOLUTIONS_STAMP = (-1, -1, -1)
        return licenseid_resolve(*args)

    with patch("pitloom.extract._license.resolve", side_effect=resolve_during_change):
        assert resolve_declared_value("Apache2") is not None
    assert not _license._RESOLUTIONS


def test_each_caller_gets_its_own_copy_of_an_answer() -> None:
    first = resolve_declared_value("Apache2")
    assert first is not None and first["steps"]
    first["steps"].clear()
    second = resolve_declared_value("Apache2")
    assert second is not None and second["steps"]


def test_the_database_stamp_is_the_files_or_none(tmp_path: Path) -> None:
    db = tmp_path / "licenses.db"
    db.write_bytes(b"x")
    st = db.stat()
    assert _license._database_stamp(db) == (st.st_mtime_ns, 1, st.st_ino)
    assert _license._database_stamp(tmp_path / "missing.db") is None


def test_no_notes_when_the_resolver_has_no_reading_now() -> None:
    """The resolver names no licence (``Acme2``, even with the database):
    no note is written."""
    assert _license_resolve.resolution_notes("Acme2", "MIT") == ""
