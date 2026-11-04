# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared licence value read through ``licenseid.resolve``, its only
reader: every answer with an expression is recorded (``Apache2`` is
``Apache-2.0``, ``GPLv3`` is ``GPL-3.0``), how it is said (``INFO:`` once,
the provenance keys), and what stays text (several licences, a compound
with an unreadable part, a character the resolver drops). The reading uses
the SPDX License List packaged with ``licenseid``: no database.

See also: tests/extract/test_license_spdx_only_fields.py (the warning for a
value nothing reads) and docs/metadata-provenance-licences.md.
"""

# pylint: disable=protected-access

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from licenseid import DatabaseNotReadyError
from licenseid import resolve as licenseid_resolve

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.extract import _license_resolve, _license_text_match
from pitloom.extract._license import (
    classify_license,
    clear_resolution_cache,
    resolve_declared_value,
    tag_deprecated_license_ids,
    tag_license_normalization,
    warn_unless_expression,
)
from tests._license_graph import license_elements

_LOGGER = "pitloom.extract._license_resolve"
_CLASSPATH = "GPL-2.0 WITH Classpath-exception-2.0"
_NOKIA = "GPL-2.0-or-later WITH Nokia-Qt-exception-1.1"
_PLUS = " | Expansion-1: plus_to_or_later"


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
        ("MIT :", "MIT", "separator"),  # an end mark the resolver drops
        ("BSD 3-Clause License", "BSD-3-Clause", "prose_form, separator"),
        ("standardml-nj", "SMLNJ", "id_case, deprecated_equal_successor"),
        ("Apache2 OR MIT", "Apache-2.0 OR MIT", "separator, version_spelling"),
        # a deprecated id kept as written beside a re-spelt one: decided
        ("Apache2 OR GPL-2.0", "Apache-2.0 OR GPL-2.0", "separator, version_spelling"),
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
        "end-mark",
        "prose",
        "renamed",
        "compound",
        "compound-deprecated",
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
    ("raw", "normalized", "expansion"),
    [
        ("mit", "MIT", ""),
        ("MIT AND MIT", "MIT", ""),
        ("GPL-2.0+", "GPL-2.0-or-later", " | Expansion-1: plus_to_or_later"),
        ("(GPL-3.0+)", "GPL-3.0-or-later", " | Expansion-1: plus_to_or_later"),
        # a deprecated id kept as written, its spacing or "+" changed
        ("GPL-2.0 WITH  Classpath-exception-2.0", _CLASSPATH, ""),
        ("gpl-2.0 with  classpath-exception-2.0", _CLASSPATH, ""),
        ("GPL-2.0+ WITH Nokia-Qt-exception-1.1", _NOKIA, _PLUS),
        ("GPL-2.0+ WITH  Nokia-Qt-exception-1.1", _NOKIA, _PLUS),
    ],
    ids=["case", "dup", "plus", "plus-parens", "with-ws", "with-case", "with-plus",
         "with-plus-ws"],
)  # fmt: skip
def test_a_change_of_form_names_licenseid_and_no_decision(
    raw: str, normalized: str, expansion: str, caplog: pytest.LogCaptureFixture
) -> None:
    """``licenseid`` did the rewrite, so ``Tool`` names it; it decided nothing
    beyond form and ``+``, so there is no ``Method`` or ``Resolution-1``, and
    nothing is said above ``DEBUG:``."""
    tool = f"licenseid=={licenseid_resolve('MIT')['resolver']['version']}"
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and got.value == normalized
    assert not _said(caplog, logging.INFO)
    assert tag_license_normalization("P", raw, normalized) == (
        f"P | Normalized-From: {raw}{expansion} | Tool: {tool}"
    )


@pytest.mark.parametrize(
    ("raw", "expression"),
    [
        ("GPLv2+ WITH Nokia-Qt-exception-1.1", _NOKIA),
        ("GPL-2+ WITH Nokia-Qt-exception-1.1", _NOKIA),
        ("GPLv2 WITH  Classpath-exception-2.0", _CLASSPATH),
        ("GPLv3  OR MIT", "GPL-3.0 OR MIT"),
    ],
    ids=["respelt-plus", "short-version-plus", "respelt-ws", "respelt-or"],
)
def test_a_respelling_beside_a_change_of_form_is_still_a_decision(
    raw: str, expression: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Undoing spacing and ``+`` leaves the re-spelling: said and noted."""
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and got.value == expression
    (info,) = _said(caplog, logging.INFO)  # the excerpt collapses spacing
    assert f": read as {expression} (" in info
    assert f"Resolution-1: {raw} -> {expression} (" in tag_license_normalization(
        "P", raw, expression
    )


def _answer(category: str, operand: str = "MIT") -> Any:
    """A ``licenseid`` answer of *category*, with one applied step and one
    that was declined, read from one *operand* of that category."""
    steps = [
        {"kind": "trim", "applied": False},
        {"kind": "id_case", "applied": True},
    ]
    return {
        "expression": "MIT",
        "category": category,
        "steps": steps,
        "expansions": [],
        "operands": [
            {"text": operand, "expression": "MIT", "category": category,
             "expansions": [], "candidates": []},
        ],
        "resolver": {"name": "licenseid", "version": "9.9"},
    }  # fmt: skip


@pytest.mark.parametrize(
    ("category", "operand", "decided"),
    [
        ("exact", "MIT", False),
        ("lexical", "MIT", False),
        ("plus_to_or_later", "MIT", False),
        ("separator", "MIT", True),
        ("deprecated_equal_successor", "MIT", True),
        # a deprecated id kept as written, in any case, is the author's
        ("assumed_only", "mit", False),
        ("deprecated_ambiguous", "MIT", False),
        # re-spelt to reach it, it is the resolver's
        ("assumed_only", "MITv1", True),
        ("deprecated_ambiguous", "MIT1", True),
    ],
)
def test_only_a_decision_beyond_form_is_said_at_info_and_noted(
    category: str, operand: str, decided: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """Case, spacing, ``+`` and a deprecated id as written are the author's
    licence: ``DEBUG:`` and no ``Method``/``Resolution-1``; a declined step
    is not listed; ``Tool`` names the resolver of the answer."""
    answer = _answer(category, operand)
    with (
        caplog.at_level(logging.DEBUG, logger=_LOGGER),
        patch("pitloom.extract._license_resolve.resolve", return_value=answer),
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
    assert note.endswith(" | Tool: licenseid==9.9")
    assert (note == " | Tool: licenseid==9.9") is not decided


def test_the_answer_is_recorded_as_licenseid_gives_it() -> None:
    """No second parser checks the answer: ``licenseid`` is the only reader."""
    answer = _answer("separator") | {"expression": "Not-A-Listed-Id"}
    with patch("pitloom.extract._license_resolve.resolve", return_value=answer):
        got = classify_license("Apache 2.0+", warn=False)
    assert got is not None
    assert (got.kind, got.value) == ("expression", "Not-A-Listed-Id")


def test_a_value_is_said_once_by_its_text_not_by_its_reading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        classify_license("Apache2")
        classify_license("Apache 2.0")  # the same expression, another value
    assert len(_said(caplog, logging.INFO)) == 2


def test_the_answers_are_kept_when_the_database_is_found_unusable() -> None:
    """They do not rest on the database: only the detector is dropped."""
    resolve_declared_value("Apache2")
    _license_text_match._database_unusable(RuntimeError("x"))
    assert _license_resolve._resolved.cache_info().currsize == 1


def test_the_reading_is_the_same_with_and_without_a_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The packaged list decides, not the user's database (none here)."""
    with_db = resolve_declared_value("Apache2")
    assert with_db is not None and with_db["expression"] == "Apache-2.0"
    clear_resolution_cache()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert resolve_declared_value("Apache2") == with_db
    assert [entry["source"] for entry in with_db["lists"]] == ["packaged"]


@pytest.mark.parametrize(
    "raw",
    [
        "BSD",  # several licences
        "GPL",
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
        "MIT ; Apache 2",  # licences joined by no operator
        "GPLv3 +",  # a plus after a space
    ],
)
def test_a_value_naming_no_single_licence_stays_text(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None and got.kind == "text"
    # a lone surrogate is replaced by U+FFFD on the way in
    assert got.value == re.sub("[\ud800-\udfff]", "\ufffd", raw.strip())


@pytest.mark.parametrize("raw", ["GPL-3.0", "GPL-2.0", "LGPL-2.1"])
def test_a_bare_deprecated_id_is_never_narrowed(
    raw: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Kept as written, quiet, its two possible successors noted."""
    with caplog.at_level(logging.INFO, logger="pitloom"):
        got = classify_license(raw)
    assert got is not None
    assert (got.kind, got.value) == ("expression", raw)
    assert not caplog.records
    assert tag_deprecated_license_ids("P", raw) == (
        f"P | Deprecated-License-Id: {raw} ({raw}-only or {raw}-or-later)"
    )


@pytest.mark.parametrize(
    ("raw", "expression"),
    [("GPLv3", "GPL-3.0"), ("AGPLv3", "AGPL-3.0"), ("GPL v2", "GPL-2.0"),
     ("LGPLv2.1", "LGPL-2.1")],
)  # fmt: skip
def test_a_respelt_deprecated_id_is_read_as_that_id_not_narrowed(
    raw: str, expression: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The resolver finds the deprecated id but not its ``-only``/``-or-later``
    (``assumed_only``): the id is recorded as the author stated it, the
    re-spelling said and noted, its successors noted, none chosen."""
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        got = classify_license(raw)
    assert got is not None and (got.kind, got.value) == ("expression", expression)
    (info,) = _said(caplog, logging.INFO)
    assert info.startswith(f"LICENSE={raw!r}: read as {expression} (")
    note = tag_deprecated_license_ids(
        tag_license_normalization("P", raw, expression), expression
    )
    assert f"Resolution-1: {raw} -> {expression} (" in note
    assert note.endswith(
        f" | Deprecated-License-Id: {expression}"
        f" ({expression}-only or {expression}-or-later)"
    )


def test_a_deprecated_id_with_an_exception_is_noted_without_it() -> None:
    expression = "GPL-2.0 WITH Classpath-exception-2.0 OR MIT OR GPL-2.0"
    assert tag_deprecated_license_ids("P", expression) == (
        "P | Deprecated-License-Id: GPL-2.0 (GPL-2.0-only or GPL-2.0-or-later)"
    )


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


_NO_LIST = "spdx-bundle.json.gz: not found: packaged data"


@pytest.mark.parametrize(
    "failure",
    [DatabaseNotReadyError(_NO_LIST, "not found"), RuntimeError("boom")],
    ids=["no-packaged-list", "resolver-error"],
)
def test_no_reading_when_the_resolver_cannot_answer(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """No packaged list (a ``licenseid`` installed without it) or a failing
    resolver leaves the value as text; the missing list is warned once, a
    resolver bug is a debug."""
    with (
        caplog.at_level(logging.DEBUG, logger="pitloom"),
        patch("pitloom.extract._license_resolve.resolve", side_effect=failure),
    ):
        got = classify_license("Apache2", warn=False)
        classify_license("Apache2", warn=False)
    assert got is not None and (got.kind, got.value) == ("text", "Apache2")
    unusable = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.getMessage() == f"licenseid: {_NO_LIST}"
    ]
    assert len(unusable) == (1 if isinstance(failure, DatabaseNotReadyError) else 0)


@pytest.mark.parametrize(
    "category",
    ["prose_form", "trove_name", "assumed_only", "deprecated_ambiguous",
     "stated_qualifier", "version_spelling"],
)  # fmt: skip
def test_every_answer_with_an_expression_is_accepted(category: str) -> None:
    with patch(
        "pitloom.extract._license_resolve.resolve", return_value=_answer(category)
    ):
        got = classify_license("Acme2", warn=False)
    assert got is not None and (got.kind, got.value) == ("expression", "MIT")


@pytest.mark.parametrize("category", ["malformed", "unresolved"])
def test_an_answer_without_an_expression_is_text_with_its_reason(
    category: str,
) -> None:
    answer = _answer(category) | {"expression": None, "reason": "not found: Acme2"}
    with patch("pitloom.extract._license_resolve.resolve", return_value=answer):
        got = classify_license("Acme2", warn=False)
        assert _license_resolve.refusal_reason("Acme2") == "not found: Acme2"
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


def test_a_value_is_resolved_once_and_a_failure_is_not_remembered() -> None:
    """Callers share one answer per value; a failed answer is asked again."""
    real = licenseid_resolve
    with patch("pitloom.extract._license_resolve.resolve", side_effect=real) as spy:
        for _ in range(3):
            classify_license("Apache2", warn=False)
        assert spy.call_count == 1
        assert spy.call_args.kwargs == {"source": "packaged"}
    with patch(
        "pitloom.extract._license_resolve.resolve",
        side_effect=[RuntimeError("boom"), None],
    ) as flaky:
        assert resolve_declared_value("Acme2") is None
        assert resolve_declared_value("Acme2") is None  # asked again, not cached
        assert flaky.call_count == 2


def test_the_answers_are_bounded() -> None:
    for value in ("Acme1", "Acme2", "Acme3"):
        resolve_declared_value(value)
    info = _license_resolve._resolved.cache_info()
    assert (info.currsize, info.maxsize) == (3, _license_resolve._MAX_RESOLUTIONS)


def test_each_caller_gets_its_own_copy_of_an_answer() -> None:
    first = resolve_declared_value("Apache2")
    assert first is not None and first["steps"]
    first["steps"].clear()
    second = resolve_declared_value("Apache2")
    assert second is not None and second["steps"]


def test_no_notes_when_the_resolver_has_no_reading_now() -> None:
    """The resolver names no licence (``Acme2``, even with the database):
    no note is written."""
    assert _license_resolve.resolution_notes("Acme2", "MIT") == ""
