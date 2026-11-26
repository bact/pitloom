# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Rules over the whole catalogue that no one entry can check: one subject
key names one kind of value, an ``INFO:``-only entry is a decision nobody
acts on (rule R1, forward-only), and the prose is British.

See also: tests/messages/test_messages_types.py (each entry's own rules),
tests/messages/test_messages_line_since.py (``since`` against the last
release), working-docs/design/message-consistency-rescan.md (the rulings).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Final

import pytest

from pitloom.messages import MESSAGES, Message
from pitloom.messages._catalogue import SUMMARIES
from pitloom.messages._fields import FIELDS
from pitloom.messages._summary import Summary

#: Each subject key a line may print, and the fields its value may come
#: from. ``FIELD=`` names a project metadata key (``field``) or a dataset
#: field (``dataset_field``): one key, two value domains.
SUBJECT_FIELDS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "ARCHIVE": frozenset({"archive"}),
        "AUTHOR": frozenset({"authors"}),
        "AUTHOR_EMAIL": frozenset({"authors"}),
        "CLASSIFIERS": frozenset({"classifiers"}),
        "DATASET": frozenset({"dataset"}),
        "DIR": frozenset({"dir"}),
        "ELEMENT": frozenset({"spdx_id"}),
        "ENTRY": frozenset({"member"}),
        "FIELD": frozenset({"field", "dataset_field"}),
        "FILE": frozenset({"file"}),
        "FINGERPRINT": frozenset({"fingerprint"}),
        "FORMAT": frozenset({"format"}),
        "LICENSE": frozenset({"license"}),
        "LINE": frozenset({"line_number"}),
        "MAINTAINER": frozenset({"authors"}),
        "MAINTAINER_EMAIL": frozenset({"authors"}),
        "MARKER": frozenset({"name"}),
        "MODEL": frozenset({"model"}),
        "PACKAGE": frozenset({"package"}),
        "PYPI": frozenset({"name"}),
        "RELATIONSHIP": frozenset({"name"}),
        "REQUIREMENT": frozenset({"name"}),
        "SOURCE": frozenset({"dataset_source"}),
        "SOURCE_DATE_EPOCH": frozenset({"value"}),
        "URL": frozenset({"url"}),
        "VERSION": frozenset({"version"}),
    }
)

#: The fields whose value is itself a subject key (``%(key)s=%(name)s``),
#: and the field each takes its value from: ``over-cap``'s one line for any
#: input writes ``FILE=``, ``DIR=`` and the rest by the ``name`` field.
_KEY_FIELDS: Final[Mapping[str, str]] = MappingProxyType(
    {"key": "name", "author_key": "authors"}
)

#: ``KEY=%(field)s``, a key not inside a word or a placeholder.
_SUBJECT: Final = re.compile(r"(?<![\w%])([A-Z][A-Z0-9_]*)=%\((\w+)\)s")
#: ``KEY=`` followed by anything but a placeholder.
_BARE_SUBJECT: Final = re.compile(r"(?<![\w%])([A-Z][A-Z0-9_]*)=(?!%\()")
#: ``%(key)s=%(field)s``.
_KEYED: Final = re.compile(r"%\((\w+)\)s=%\((\w+)\)s")


def _templates() -> Iterator[tuple[str, str]]:
    for code, entry in MESSAGES.items():
        for line in entry.lines:
            yield code, line.template


def test_every_subject_key_names_its_one_kind_of_value() -> None:
    wrong = [
        (code, key, field)
        for code, template in _templates()
        for key, field in _SUBJECT.findall(template)
        if field not in SUBJECT_FIELDS.get(key, frozenset())
    ]
    assert not wrong


def test_no_subject_key_prints_a_literal_value() -> None:
    assert not [
        (code, key)
        for code, template in _templates()
        for key in _BARE_SUBJECT.findall(template)
    ]


@pytest.mark.parametrize(
    ("template", "keys"),
    [
        ("FILE=%(file)s MODEL=%(model)s: x", [("FILE", "file"), ("MODEL", "model")]),
        ("in a list (MODEL=%(model)s)", [("MODEL", "model")]),
        ("%(key)s=%(name)s: x", []),
        ("a%(x)s=%(y)s", []),
    ],
    ids=["pair", "in-parentheses", "key-field", "placeholder-name"],
)
def test_a_subject_key_is_found_wherever_it_stands(
    template: str, keys: list[tuple[str, str]]
) -> None:
    assert _SUBJECT.findall(template) == keys


def _key_spellings(name: str) -> list[str]:
    return FIELDS[name].pattern.split("|")


def test_a_key_field_takes_only_subject_keys_and_its_one_value() -> None:
    keyed = {
        (key, value)
        for _, template in _templates()
        for key, value in _KEYED.findall(template)
    }
    assert keyed == set(_KEY_FIELDS.items())
    for name in _KEY_FIELDS:
        assert set(_key_spellings(name)) <= set(SUBJECT_FIELDS), name


def test_every_subject_key_is_printed() -> None:
    printed = {
        key for _, template in _templates() for key, _ in _SUBJECT.findall(template)
    }
    printed.update(key for name in _KEY_FIELDS for key in _key_spellings(name))
    assert printed == set(SUBJECT_FIELDS)


#: ``INFO:``-only entries whose effect or actor is not ``none``: each was
#: ruled so before rule R1 (an ``INFO:`` line is a decision nobody acts on)
#: was made forward-only, or by its own ruling since. A new one fails.
R1_OUTLIERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "reader-unsafe": "released 0.22.0",
        "reader-unsafe/remote": "released 0.23.4",
        "field-not-recordable": "released 0.23.0",
        "usage-unparseable/mention": "released 0.22.1",
        "release-unpinned": "released 0.24.0",
        "release-unpinned/prerelease": "released 0.24.0",
        "release-unpinned/yanked": "released 0.24.0",
        "release-unusable": "released 0.24.0",
        "file-ambiguous": "released 0.24.0",
        "git-link-unsafe": "catalogue PR 13, Q13: the links are removed",
        "dependency-name-ambiguous": "catalogue PRs 10-11, Q6",
        "option-missing/project-dir": "catalogue PR 16, E5",
    }
)


def test_an_info_only_entry_is_a_decision_nobody_acts_on() -> None:
    found = {
        code
        for code, entry in MESSAGES.items()
        if entry.levels == {"INFO"} and (entry.effect, entry.actor) != ("none", "none")
    }
    assert found == set(R1_OUTLIERS)


#: Words spelt the American way where Pitloom writes British prose.
_AMERICAN: Final = re.compile(
    r"\b\w+(?:iz|yz)(?:e|ed|es|ing|ation|ations)\b"
    r"|\b(?:behaviors?|colors?|centers?|catalogs?|gray|"
    r"(?:cancel|label|model|travel)(?:ed|ing)|favor(?:s|ed|ing|ite)?|"
    r"honor(?:s|ed|ing)?|defense|fulfill(?:s|ment)?|license|licenses)\b",
    re.IGNORECASE,
)
#: British spellings the pattern above also matches.
_BRITISH: Final = frozenset({"size", "sized", "seize"})
#: Words a line quotes as written elsewhere: a specification's term, a
#: tool's own text, a product, a field or key name.
_QUOTED: Final = (
    re.compile(r"%\(\w+\)s"),
    re.compile(r"\b[\w.-]*[_.][\w.-]*\b"),  # identifiers: license_name, a.license
    re.compile(r"\b[a-z]+(?:-[a-z0-9]+)+\b"),  # codes, caps: license-detection
    re.compile(r"\b[A-Z][A-Za-z]*License\w*\b|\bLicense(?:ID|Ref|-Expression)\b"),
    re.compile(r"\bSPDX license expressions?\b|\bSPDX License List\b"),
    re.compile(r"\bLicense ::|\bSPDX-License-Identifier\b"),
    re.compile(r"\bLICENSE="),
    re.compile(r"\bunrecognized arguments\b"),  # argparse's own words
    re.compile(r"\banalyzed\b"),  # the SPDX 3 sbomType
)
#: Words an entry is let keep, by code: a card key ``card-malformed`` names
#: as the card writes it, a licence name quoted as written (``MIT
#: License``), and the core metadata field ``license-ambiguous`` names in
#: lower case (licence-detection modules are fenced off from the rescan: a
#: follow-up in the rescan doc).
_KEPT: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "card-malformed": frozenset({"license"}),
        "license-ambiguous": frozenset({"license"}),
        "license-expression-invalid/resolved": frozenset({"License"}),
    }
)


def _prose(entry: Message) -> Iterator[str]:
    yield from (line.template for line in entry.lines)
    yield from (entry.summary, entry.did, entry.advice)


def _summary_prose(summary: Summary) -> Iterator[str]:
    yield from (summary.template, summary.meaning)


def _american(text: str) -> list[str]:
    for pattern in _QUOTED:
        text = pattern.sub(" ", text)
    return [word for word in _AMERICAN.findall(text) if word.lower() not in _BRITISH]


@pytest.mark.parametrize("code", sorted(MESSAGES))
def test_an_entry_is_written_in_british_english(code: str) -> None:
    kept = _KEPT.get(code, frozenset())
    assert not [
        w for text in _prose(MESSAGES[code]) for w in _american(text) if w not in kept
    ]


def test_a_summary_is_written_in_british_english() -> None:
    assert not [
        w
        for summary in SUMMARIES
        for text in _summary_prose(summary)
        for w in _american(text)
    ]


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("could not be recognized", ["recognized"]),
        ("the license file", ["license"]),
        ("an SPDX license expression", []),
        ("License :: OSI Approved", []),
        ("general.license", []),
        ("the license-detection cap", []),
        ("LicenseID reads", []),
        ("normalised, recognised", []),
        ("colors, behaviors, catalogs", ["colors", "behaviors", "catalogs"]),
        ("modeling, labeled, favor, honor", ["modeling", "labeled", "favor", "honor"]),
        ("licensed under, a licence, fulfil, defence, favour", []),
    ],
    ids=[
        "ize",
        "noun",
        "spec",
        "classifier",
        "key",
        "cap",
        "product",
        "british",
        "plurals",
        "verb-forms",
        "british-forms",
    ],
)
def test_the_lint_finds_american_words_only(text: str, found: list[str]) -> None:
    assert _american(text) == found


#: A line's subject: ``KEY=%(value)s`` pairs, a ``%(key)s=%(name)s`` pair or
#: a bare value (a path, a URL) up to the first ``: ``.
_SUBJECT_HEAD: Final = re.compile(
    r"^(?:(?:[A-Z][A-Z0-9_]*=|%\(\w+\)s=)?%\(\w+\)s[ :])*?"
    r"(?:[A-Z][A-Z0-9_]*=|%\(\w+\)s=)?%\(\w+\)s: "
)
_PLACEHOLDER: Final = re.compile(r"%\(\w+\)s")
#: The CLI metavar a registry line names a walked path by (``PATH %(path)s``).
_BARE_PATH_HEAD: Final = re.compile(r"^PATH %\(path\)s: ")
#: Sub-prefixes a line opens with inside its template.
_SUB_PREFIXES: Final = (
    "ID registry: ",
    "Merge: ",
    "loom SDK: ",
    "Options: ",
    "Build: ",
    "dataset metadata: ",
)
#: Names a condition may open with: a product, a format, an acronym, an
#: environment variable.
_NAME_START: Final = re.compile(
    r"(?:[A-Z][A-Z0-9_]+\b(?!=)|[A-Z][a-z]+[A-Z]\w*|"
    r"Croissant|Flit|Git|Hatchling|Hugging|PyPI|Pitloom|Python)\b"
)
#: Lines out of the rule, by code: a licence module is fenced off from the
#: rescan (a follow-up in the rescan doc).
_CAPITAL_KEPT: Final = frozenset({"license-relationship-invalid"})


def _condition(template: str) -> str:
    """*template* without its sub-prefix, then its subject
    (``ID registry: FILE=%(file)s: ...``, ``Build: %(name)s: ...``)."""
    for prefix in _SUB_PREFIXES:
        template = template.removeprefix(prefix)
    template = _SUBJECT_HEAD.sub("", template, count=1)
    return _BARE_PATH_HEAD.sub("", template, count=1)


@pytest.mark.parametrize(
    ("template", "condition"),
    [
        ("FILE=%(file)s MODEL=%(model)s: model file", "model file"),
        ("%(key)s=%(name)s: larger", "larger"),
        ("%(path)s: no Python project", "no Python project"),
        ("ID registry: model %(entity)s: no entry", "model %(entity)s: no entry"),
        ("ID registry: FILE=%(file)s: Duplicate", "Duplicate"),
        ("ID registry: PATH %(path)s: Not indexed", "Not indexed"),
        ("Build: %(name)s: %(option)s has", "%(option)s has"),
        ("Failed to read", "Failed to read"),
    ],
    ids=[
        "keys",
        "key-field",
        "bare",
        "sub-prefix",
        "sub-prefix-then-key",
        "sub-prefix-then-path",
        "frame-then-bare",
        "no-subject",
    ],
)
def test_the_condition_follows_the_subject(template: str, condition: str) -> None:
    assert _condition(template) == condition


def test_a_condition_opens_in_lower_case_with_no_full_stop() -> None:
    """``LEVEL: [SUBJECT=value: ]CONDITION[; ACTION]``: the condition is no
    sentence, so it opens in lower case (a name excepted) and ends with no
    full stop."""
    capital = [
        (code, line.template)
        for code, entry in MESSAGES.items()
        if code not in _CAPITAL_KEPT
        for line in entry.lines
        if _condition(line.template)[:1].isupper()
        and not _NAME_START.match(_condition(line.template))
    ]
    stop = [
        (code, line.template)
        for code, entry in MESSAGES.items()
        for line in entry.lines
        if line.template.endswith(".") and not line.template.endswith("...")
    ]
    assert (capital, stop) == ([], [])


def test_an_entry_says_directory_never_folder() -> None:
    """One word for one thing: ``directory``, as the ``DIR=`` key says, in
    every line, summary, did and advice."""
    folder = re.compile(r"\b(?:sub)?folders?\b", re.IGNORECASE)
    texts = [
        (code, text) for code, entry in MESSAGES.items() for text in _prose(entry)
    ] + [
        (summary.template, text)
        for summary in SUMMARIES
        for text in _summary_prose(summary)
    ]
    assert not [
        (where, text)
        for where, text in texts
        if folder.search(_PLACEHOLDER.sub(" ", text))
    ]


@pytest.mark.parametrize(
    ("condition", "named"),
    [
        ("PyTorch archive", True),
        ("HF_ENDPOINT not used", True),
        ("Hatchling version", True),
        ("Failed to read", False),
        ("Duplicate key", False),
        ("FILE=%(file)s Failed", False),
    ],
    ids=["camel", "variable", "product", "verb", "word", "subject-key"],
)
def test_only_a_name_may_open_a_condition_in_capitals(
    condition: str, named: bool
) -> None:
    assert bool(_NAME_START.match(condition)) is named
