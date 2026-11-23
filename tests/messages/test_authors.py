# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``author-ambiguous``, ``author-invalid`` and ``project-unreadable``: the
line each helper picks, and an author field (attacker text) shown masked,
cut and escaped on one trusted line.

See also: :mod:`pitloom.messages._authors`,
:mod:`tests.test_author_code_surfaces` (each surface).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import re

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, EXCERPT_CHARS
from pitloom.messages import trusted_message
from pitloom.messages._field_writers import NAME_CHARACTERS
from pitloom.messages._fields_authors import AUTHOR_FIELDS
from pitloom.messages.authors import (
    ADDRESS_SPLIT_LINE,
    AUTHOR_AMBIGUOUS,
    AUTHOR_INVALID,
    DEPENDENCY_ADDRESS_SPLIT_LINE,
    DEPENDENCY_NAME_SPLIT_LINE,
    EMAIL_INVALID_COUNT_LINE,
    EMAIL_INVALID_LINE,
    NAME_INVALID_COUNT_LINE,
    NAME_INVALID_LINE,
    NAME_SPLIT_LINE,
    ONE_AUTHOR_LINE,
    PROJECT_UNREADABLE,
    authors_text,
    note_one_author,
    warn_author_split,
    warn_dependency_split,
    warn_not_addresses,
    warn_project_unreadable,
)

_LOG = logging.getLogger("pitloom.authors_test")


def _records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _LOG.name]


def _printed(record: logging.LogRecord) -> str:
    return f"{record.levelname}: {record.getMessage()} [{getattr(record, CODE_ATTR)}]"


@pytest.mark.parametrize(
    ("named", "line", "key"),
    [(True, NAME_SPLIT_LINE, "AUTHOR="), (False, ADDRESS_SPLIT_LINE, "AUTHOR_EMAIL=")],
    ids=["name-field", "address-field"],
)
def test_a_split_picks_its_line_by_field_kind(
    caplog: pytest.LogCaptureFixture, named: bool, line: object, key: str
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        warn_author_split(_LOG, ["a, b", "c; d"], 4, named=named)
    (record,) = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage().startswith(
        f"{key}['a, b', 'c; d']: split into 4 entries"
    )
    assert record.msg == line.template  # type: ignore[attr-defined]
    assert trusted_message(_printed(record)) is AUTHOR_AMBIGUOUS


def test_one_author_is_an_info_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        note_one_author(_LOG, ["Ann and Bob"])
    (record,) = _records(caplog)
    assert record.levelno == logging.INFO and record.msg == ONE_AUTHOR_LINE.template
    assert record.getMessage() == (
        "AUTHOR='Ann and Bob': read as one author; it may list several"
    )
    assert trusted_message(_printed(record)) is AUTHOR_AMBIGUOUS


@pytest.mark.parametrize(
    ("named", "line", "dependencies", "count"),
    [
        (True, DEPENDENCY_NAME_SPLIT_LINE, 1, "1 dependency"),
        (False, DEPENDENCY_ADDRESS_SPLIT_LINE, 3, "3 dependencies"),
    ],
    ids=["name-one", "address-several"],
)
def test_a_dependency_split_names_the_package_and_the_count(
    caplog: pytest.LogCaptureFixture,
    named: bool,
    line: object,
    dependencies: int,
    count: str,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dependency_split(
            _LOG,
            "demo",
            "MAINTAINER_EMAIL",
            "a, b",
            2,
            named=named,
            dependencies=dependencies,
        )
    (record,) = _records(caplog)
    text = record.getMessage()
    assert text.startswith("PACKAGE=demo MAINTAINER_EMAIL='a, b': split into 2 entries")
    assert text.endswith(f"; {count} split in all")
    assert record.msg == line.template  # type: ignore[attr-defined]
    assert trusted_message(_printed(record)) is AUTHOR_AMBIGUOUS


@pytest.mark.parametrize(
    "package",
    # the cut falls just before the '@': masked first, or the secret shows
    ["p" * 1_000_000, "p" * 481 + "https://u:pw-s3cr3t@example.org/x"],
    ids=["1mb", "credential-at-cut"],
)
def test_a_long_package_name_is_masked_then_cut(
    caplog: pytest.LogCaptureFixture, package: str
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_dependency_split(
            _LOG, package, "AUTHOR", "a, b", 2, named=True, dependencies=1
        )
    (record,) = _records(caplog)
    printed = _printed(record)
    assert "pw-s3cr3t" not in printed
    assert len(printed) < NAME_CHARACTERS + 300
    assert printed.startswith(f"WARNING: PACKAGE={'p' * 481}")
    assert trusted_message(printed) is AUTHOR_AMBIGUOUS


@pytest.mark.parametrize(
    ("key", "entries", "line", "tail"),
    [
        ("AUTHOR_EMAIL", ["x"], EMAIL_INVALID_LINE, "; not recorded"),
        (
            "AUTHOR_EMAIL",
            ["x", "y"],
            EMAIL_INVALID_COUNT_LINE,
            "; 2 entries not recorded",
        ),
        ("AUTHOR", ["x"], NAME_INVALID_LINE, "; not recorded"),
        ("AUTHOR", list("abcde"), NAME_INVALID_COUNT_LINE, "; 5 entries not recorded"),
    ],
    ids=["email-one", "email-two", "name-one", "name-five"],
)
def test_not_an_address_picks_its_line_by_key_and_count(
    caplog: pytest.LogCaptureFixture,
    key: str,
    entries: list[str],
    line: object,
    tail: str,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_not_addresses(_LOG, key, entries)
    (record,) = _records(caplog)
    assert record.getMessage().startswith(f"{key}=")
    assert record.getMessage().endswith(f"not an email address{tail}")
    assert record.msg == line.template  # type: ignore[attr-defined]
    assert trusted_message(_printed(record)) is AUTHOR_INVALID


@pytest.mark.parametrize(
    ("key", "entries"),
    [("MAINTAINER_EMAIL", ["x"]), ("AUTHOR", [])],
    ids=["dependency-key", "empty"],
)
def test_not_an_address_refuses_what_no_line_says(key: str, entries: list[str]) -> None:
    with pytest.raises(InternalError):
        warn_not_addresses(_LOG, key, entries)


def test_project_unreadable_names_the_directory_and_the_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        warn_project_unreadable(_LOG, "proj", ValueError("bad\nWARNING: x [code]"))
    (record,) = _records(caplog)
    text = record.getMessage()
    assert text.startswith(
        "DIR=proj: project metadata not read; authors from the wheel"
    )
    assert "\n" not in text
    assert trusted_message(_printed(record)) is PROJECT_UNREADABLE


_SECRET = "pw-s3cr3t"


@pytest.mark.parametrize(
    "field",
    [
        "a\nWARNING: forged [author-invalid]",
        "\x1b[31mred\x1b[0m",
        f"https://u:{_SECRET}@example.org/x",
        "Doe, J" + "x" * 1_000_000,
        'O\'Brien, "Q"',
        "ends [author-ambiguous]",
    ],
    ids=["newline", "ansi", "credential", "1mb", "quotes", "forged-code"],
)
def test_a_hostile_author_field_is_one_trusted_line(
    caplog: pytest.LogCaptureFixture, field: str
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        warn_author_split(_LOG, [field], 2, named=False)
        note_one_author(_LOG, [field])
        warn_not_addresses(_LOG, "AUTHOR_EMAIL", [field])
        warn_dependency_split(_LOG, "p", "AUTHOR", field, 2, named=True, dependencies=1)
    records = _records(caplog)
    assert len(records) == 4
    for record in records:
        printed = _printed(record)
        assert "\n" not in printed and "\x1b" not in printed
        assert _SECRET not in printed
        assert len(printed) < 2 * EXCERPT_CHARS + 200
        assert trusted_message(printed) is not None


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("a", "'a'"),
        (["a"], "'a'"),
        (("a", "b"), "['a', 'b']"),
        (["a", "b", "c", "d"], "['a', 'b', 'c', ...]"),
    ],
    ids=["str", "one", "two", "four"],
)
def test_authors_shows_at_most_three_fields(value: object, shown: str) -> None:
    assert authors_text(value) == shown


@pytest.mark.parametrize("value", [[], None, 3, ["a", 3], object()])
def test_authors_refuses_what_is_no_field(value: object) -> None:
    with pytest.raises(ValueError):
        authors_text(value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("author_key", "author"),
        ("author_key", "AUTHOR\nX"),
        ("entry_count", 0),
        ("dependency_count", -1),
    ],
    ids=["key-case", "key-newline", "no-entries", "negative"],
)
def test_a_key_or_count_writer_refuses_what_no_line_says(
    name: str, value: object
) -> None:
    with pytest.raises(ValueError):
        AUTHOR_FIELDS[name].write(value)


@pytest.mark.parametrize(
    ("name", "value", "text"),
    [
        ("entry_count", 1, "1 entry"),
        ("entry_count", 12, "12 entries"),
        ("dependency_count", 1, "1 dependency"),
        ("author_key", "MAINTAINER_EMAIL", "MAINTAINER_EMAIL"),
    ],
)
def test_a_key_or_count_writer_writes_its_pattern(
    name: str, value: object, text: str
) -> None:
    field = AUTHOR_FIELDS[name]
    assert field.write(value) == text
    assert re.fullmatch(field.pattern, text)
