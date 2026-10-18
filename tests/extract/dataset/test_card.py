# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.extract.dataset.card.read_dataset_card`: the
YAML frontmatter of a dataset directory's ``README.md``.

See also: tests/extract/dataset/test_licence.py (the licence rules),
tests/assemble/test_enrich_readme.py (the shared frontmatter reader).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.dataset_metadata import FurtherLicences
from pitloom.enrich.readme import MODEL_CARD_MAX_BYTES
from pitloom.extract.dataset import read_dataset_card


def _card(directory: Path, body: bytes, filename: str = "README.md") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(body)
    return directory


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_full_card(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Each field the card states, with its provenance naming the card by
    the directory as given; a tag of no text is left out with one
    ``WARNING:``."""
    corpus = _card(
        tmp_path / "corpus",
        b"---\nlicense: cc-by-4.0\npretty_name: My Corpus\nversion: '2.10'\n"
        b"tags:\n- nlp\n- ' text '\n- nlp\n- 3\ndescription: not read\n---\n"
        b"# Prose license: MIT is not read\n",
    )
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        meta = read_dataset_card(corpus)
    assert meta is not None
    src = f"{corpus.as_posix()}/README.md"
    assert (meta.name, meta.license, meta.version, meta.keywords) == (
        "My Corpus",
        "cc-by-4.0",
        "2.10",
        ["nlp", "text"],
    )
    assert meta.description is None
    assert meta.provenance == {
        "name": f"Source: {src} | Field: pretty_name",
        "license": f"Source: {src} | Field: license",
        "version": f"Source: {src} | Field: version",
        "keywords": f"Source: {src} | Field: tags",
    }
    assert _messages(caplog) == [
        f"dataset metadata: {src} field tags is of type int, not text; skipped"
    ]


@pytest.mark.parametrize(
    ("body", "filename", "expected"),
    [
        (b"---\nlicense: mit\n---\n", "readme.MD", ("mit", None, [])),
        (b"\xef\xbb\xbf---\nlicense: mit\n---\n", "README.md", ("mit", None, [])),
        (
            b"---\nlicense: [mit]\ntags: a, b\n---\n",
            "README.md",
            ("mit", None, ["a, b"]),
        ),
        (b"---\nversion: '2'\n---\n", "README.md", (None, "2", [])),
        (b"---\nlicense: unknown\n---\n", "README.md", (None, None, [])),
        (
            b"---\nlicense: other\nlicense_link: https://x.org/l\n---\n",
            "README.md",
            ("https://x.org/l", None, []),
        ),
        (b'---\nlicense: "\\ud800x"\n---\n', "README.md", ("\\ud800x", None, [])),
    ],
    ids=[
        "case-insensitive",
        "bom",
        "one-item-list",
        "quoted-version",
        "weak",
        "other-link",
        "lone-surrogate",
    ],
)
def test_card_shapes(
    tmp_path: Path,
    body: bytes,
    filename: str,
    expected: tuple[str | None, str | None, list[str]],
) -> None:
    """Spellings a card may use; the directory's name stands in for an
    absent ``pretty_name`` (with no provenance of its own)."""
    meta = read_dataset_card(_card(tmp_path / "ds", body, filename))
    assert meta is not None
    assert (meta.license, meta.version, meta.keywords) == expected
    assert meta.name == "ds"
    assert "name" not in meta.provenance


@pytest.mark.parametrize(
    "body",
    [
        None,
        b"# Just prose\nlicense: mit\n",
        b"---\nlicense: mit\n",
        b"---\n- a\n- b\n---\n",
        b"---\n---\n",
        b"",
    ],
    ids=[
        "no-card",
        "no-frontmatter",
        "unclosed",
        "not-a-mapping",
        "empty",
        "empty-file",
    ],
)
def test_no_metadata_is_silent(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes | None
) -> None:
    """A directory with no card, or a card with no usable frontmatter, has
    no metadata, and says nothing: nothing was stated."""
    directory = tmp_path / "ds"
    directory.mkdir()
    if body is not None:
        _card(directory, body)
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        assert read_dataset_card(directory) is None
    assert not caplog.records


def test_no_metadata_for_a_missing_directory(tmp_path: Path) -> None:
    assert read_dataset_card(tmp_path / "absent") is None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            b"---\nlicense: [mit\n---\n",
            "Failed to parse dataset-card frontmatter",
        ),
        (
            b"---\nlicense: [mit\n---\n",
            "license, license_name, license_link, version",
        ),
        (b"---\nversion: true\n---\n", "field version is of type bool, not text"),
        (b"---\nversion: 1.10\n---\n", "version is of type float, not text; quote"),
        (b"---\nversion: 2\n---\n", "version is of type int, not text; quote"),
        (b"---\nversion: 1:1:1\n---\n", "version is of type int, not text; quote"),
        (b"---\nversion: 0x1F\n---\n", "version is of type int, not text; quote"),
        (b"---\nversion: 010\n---\n", "version is of type int, not text; quote"),
        (b"---\ntags: [a, [b]]\n---\n", "field tags is of type list, not text"),
        (
            b"---\nlicense: 3\n---\n",
            "field license is of type int, not text; skipped",
        ),
    ],
    ids=[
        "malformed-yaml",
        "malformed-yaml-fields",
        "bool-version",
        "float-version",
        "int-version",
        "base-60-version",
        "hex-version",
        "octal-version",
        "nested-tag",
        "number-licence",
    ],
)
def test_unusable_card_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, body: bytes, expected: str
) -> None:
    """A card stating something unreadable is one ``WARNING:``."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        read_dataset_card(_card(tmp_path / "ds", body))
    messages = _messages(caplog)
    assert len(messages) == 1
    assert expected in messages[0]


def test_lone_surrogates_are_escaped_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A lone surrogate in a text field or a tag is written as ``\\uXXXX``,
    with one ``WARNING:`` naming the card."""
    body = b'---\nlicense: "x\\ud800"\ntags: ["t\\udc00", ok]\n---\n'
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        meta = read_dataset_card(_card(tmp_path / "ds", body))
    assert meta is not None
    assert (meta.license, meta.keywords) == ("x\\ud800", ["t\\udc00", "ok"])
    (message,) = _messages(caplog)
    assert "lone surrogates" in message and "README.md" in message


def test_card_over_the_cap(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A frontmatter not closed within the read cap is skipped with one
    ``WARNING:`` naming the dataset-card cap; one closed within it is read
    whatever follows."""
    padding = b"x" * MODEL_CARD_MAX_BYTES
    unclosed = _card(tmp_path / "a", b"---\nlicense: mit\ntitle: " + padding)
    closed = _card(tmp_path / "b", b"---\nlicense: mit\n---\n" + padding)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert read_dataset_card(unclosed) is None
        meta = read_dataset_card(closed)
    assert meta is not None and meta.license == "mit"
    messages = _messages(caplog)
    assert len(messages) == 1
    assert "dataset-card cap" in messages[0]


def test_alias_bomb_is_not_expanded(tmp_path: Path) -> None:
    """Only the keys read are looked at, so a YAML alias tree elsewhere in
    the frontmatter costs nothing; a licence that is such a tree is no
    licence."""
    levels = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    levels += [f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]" for i in range(1, 8)]
    body = "---\n" + "\n".join(levels) + "\nlicense: *a7\npretty_name: P\n---\n"
    meta = read_dataset_card(_card(tmp_path / "ds", body.encode()))
    assert meta is not None
    assert (meta.name, meta.license) == ("P", None)


@pytest.mark.parametrize(
    ("licence", "first", "further"),
    [
        ("[cc-by-sa-3.0, gfdl]", "cc-by-sa-3.0", ("gfdl",)),
        ("[MIT, mit]", "MIT", ()),
        ("[unknown, cc-by-4.0, other]", "cc-by-4.0", ()),
    ],
    ids=["two", "case-duplicate", "weak-dropped"],
)
def test_card_licence_list(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    licence: str,
    first: str,
    further: tuple[str, ...],
) -> None:
    """Each licence of a list, in order, once each, silently; one
    provenance entry for the field."""
    body = f"---\nlicense: {licence}\n---\n".encode()
    meta = read_dataset_card(_card(tmp_path / "ds", body))
    assert meta is not None
    assert meta.license == first
    assert meta.further_licenses == (
        FurtherLicences(further, "dataset card") if further else None
    )
    assert (
        meta.provenance["license"]
        == "Source: " + (tmp_path / "ds" / "README.md").as_posix() + " | Field: license"
    )
    assert not _messages(caplog)
