# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.iri`: a name becomes a valid IRI segment.

See also: tests/assemble/test_name_iri_surfaces.py (every surface emits the
sanitised id), tests/core/test_models.py (``generate_spdx_id`` and
``reserve_spdx_ids``).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pitloom.core.iri import doc_namespace, iri_segment
from pitloom.id_registry import IdRegistry


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("Stable Diffusion XL", "Stable%20Diffusion%20XL", id="space"),
        pytest.param("a#b", "a%23b", id="hash"),
        pytest.param("org/model", "org%2Fmodel", id="slash"),
        pytest.param("a?b", "a%3Fb", id="question"),
        pytest.param("100%", "100%25", id="percent"),
        # An encoded-looking name is text, not an escape: "%" is encoded too.
        pytest.param("a%20b", "a%2520b", id="percent-escape-lookalike"),
        pytest.param("x\ny\t", "x%0Ay%09", id="control"),
        pytest.param('<"{|}\\^`>', "%3C%22%7B%7C%7D%5C%5E%60%3E", id="ascii-other"),
        pytest.param("Модель é", "Модель%20é", id="unicode-with-space"),
        pytest.param(f"a{chr(0x202E)}b", "a%E2%80%AEb", id="bidi-formatting"),
        pytest.param("\ud800", "%ED%A0%80", id="lone-surrogate"),
    ],
)
def test_iri_segment_encodes_invalid_characters(name: str, expected: str) -> None:
    assert name != expected  # the input really needs sanitising
    assert iri_segment(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "",
        "sampleproject",
        "llama-3.1_8B~rc",
        "a+b@c:d!$&'()*,;=",
        "Модель模型é",
    ],
)
def test_iri_segment_keeps_valid_names_byte_identical(name: str) -> None:
    assert iri_segment(name) == name


@pytest.mark.parametrize(
    ("code_point", "kept"),
    [
        (0x9F, False),
        (0xA0, True),
        (0xD7FF, True),
        (0xE000, False),
        (0xF8FF, False),
        (0xF900, True),
        (0xFDCF, True),
        (0xFDD0, False),
        (0xFDEF, False),
        (0xFDF0, True),
        (0xFFEF, True),
        (0xFFF0, False),
        (0x10000, True),
        (0x1FFFD, True),
        (0x1FFFE, False),
        (0xDFFFD, True),
        (0xE0000, False),
        (0xE0FFF, False),
        (0xE1000, True),
        (0xEFFFD, True),
        (0xEFFFE, False),
        (0xF0000, False),
    ],
)
def test_iri_segment_ucschar_boundaries(code_point: int, kept: bool) -> None:
    """Each RFC 3987 ``ucschar`` range edge, inside and out."""
    char = chr(code_point)
    assert (iri_segment(char) == char) is kept


@pytest.mark.parametrize(
    "code_point", [0x200D, 0x200E, 0x200F, 0x2029, 0x202A, 0x202E, 0x202F]
)
def test_iri_segment_encodes_exactly_the_bidi_formatting_characters(
    code_point: int,
) -> None:
    """RFC 3987 section 4.1 bans U+200E, U+200F and U+202A to U+202E."""
    char = chr(code_point)
    banned = code_point in (0x200E, 0x200F) or 0x202A <= code_point <= 0x202E
    assert (iri_segment(char) != char) is banned


def test_iri_segment_is_injective() -> None:
    """Names that differ only by an encoded-looking form stay distinct."""
    names = ["a b", "a%20b", "a%2520b", "a+b"]
    assert len({iri_segment(name) for name in names}) == len(names)


@pytest.mark.parametrize(
    "build_namespace",
    [
        pytest.param(lambda: doc_namespace("my model", "u"), id="doc_namespace"),
        pytest.param(lambda: IdRegistry.new("my project").namespace, id="registry"),
    ],
)
def test_namespace_builders_encode_the_name(
    build_namespace: Callable[[], str],
) -> None:
    namespace = build_namespace()
    assert namespace.startswith("https://spdx.org/spdxdocs/my%20")
    assert " " not in namespace
