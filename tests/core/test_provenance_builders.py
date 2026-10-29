# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the provenance-string builders in
:mod:`pitloom.core.provenance`: :func:`sanitize_provenance_text`,
:func:`provenance_source` and :func:`provenance_segment`.

See also: :mod:`tests.core.test_provenance` (the settings),
:mod:`tests.core.test_untrusted_text` (the display-control set every
escape helper shares, the sanitiser included).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from collections.abc import Callable

import pytest

from pitloom.core.provenance import (
    PROVENANCE_SEGMENT_KEYS,
    parse_provenance_value,
    provenance_segment,
    provenance_source,
    sanitize_provenance_text,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a|b||c", "a/b//c"),
        ("a;b,c:d", "a;b,c:d"),  # documented: left as they are
        ("a\nb\rc\td", "a\nb\rc\td"),  # the comment writer and JSON escape them
        ("a\x00b", "a\\u0000b"),
        ("a\x85b", "a\\u0085b"),  # C1
        ("a\u202eb", "a\\u202eb"),
        ("a\u2028b", "a\\u2028b"),
        ("\udcff.gguf", "\\udcff.gguf"),  # os.fsdecode(b"\xff.gguf")
        ("x|\u202e\udcff\ud800", "x/\\u202e\\udcff\\ud800"),
    ],
    ids=["pipe", "kept-punct", "kept-ws", "nul", "c1", "rlo", "u2028", "lone", "all"],
)
def test_sanitize_provenance_text(text: str, expected: str) -> None:
    shown = sanitize_provenance_text(text)
    assert shown == expected
    shown.encode("utf-8")  # always writable


@pytest.mark.parametrize(
    "text",
    [
        "",
        "model.gguf",
        "src/pkg/__init__.py",
        "\u00dcn\u00efc\u00f8d\u00e9-\u30e2\u30c7\u30eb.safetensors",
        "\U0001f600.bin",
    ],
)
def test_clean_text_is_unchanged(text: str) -> None:
    assert sanitize_provenance_text(text) == text


def test_provenance_source_shapes() -> None:
    assert provenance_source("m|x.gguf") == "Source: m/x.gguf"
    assert (
        provenance_source("wheel METADATA", file="a|b\u202e.whl")
        == "Source: wheel METADATA | File: a/b\\u202e.whl"
    )


# The keys the source writes today, listed rather than read from the set.
_KEYS = [
    "Deprecated-License-Id", "Field", "File", "Method", "Normalized-From",
    "Normalizer", "Note", "Package", "Role", "Tool",
]  # fmt: skip


def test_the_keys_are_the_documented_ones() -> None:
    assert PROVENANCE_SEGMENT_KEYS == frozenset(_KEYS)


@pytest.mark.parametrize("key", [*_KEYS, "Resolution-1", "Expansion-12"])
def test_provenance_segment_appends_a_sanitised_value(key: str) -> None:
    assert (
        provenance_segment("Source: m", key, "v|\x1b")
        == f"Source: m | {key}: v/\\u001b"
    )


@pytest.mark.parametrize(
    "key",
    [
        "Source",  # provenance_source's
        "Evidence",  # evidence_segment's, a vocabulary
        "Reason",
        "field",  # spelled as written
        "Bogus",
        "Resolution-0",
        "Resolution-01",
        "Resolution-",
        "Resolution-1x",  # whole key only
        "xResolution-1",
        "Resolution-1\n",
    ],
)
def test_provenance_segment_refuses_an_unknown_key(key: str) -> None:
    with pytest.raises(ValueError, match="unknown provenance segment key"):
        provenance_segment("Source: m", key, "v")


_FORGED = "x | Evidence: not_measured | Reason: over-cap | Source: README.md"

_BUILDS: dict[str, Callable[[str], str]] = {
    "label": lambda name: provenance_segment(
        provenance_source(name), "Field", "general.name"
    ),
    "file": lambda name: provenance_segment(
        provenance_source("wheel METADATA", file=name), "Field", "Name"
    ),
    "value": lambda name: provenance_segment(
        provenance_source("m.gguf"), "Field", name
    ),
}


@pytest.mark.parametrize("where", _BUILDS)
def test_an_injected_segment_stays_one_segment(where: str) -> None:
    build = _BUILDS[where]
    benign = parse_provenance_value(build("x"))
    forged = parse_provenance_value(build(_FORGED))
    assert "|" in _FORGED and "evidence" not in forged
    assert forged.keys() == benign.keys()
