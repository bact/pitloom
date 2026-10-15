# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.core.iri.require_namespace_iri` and the
``namespace=`` argument of :meth:`pitloom.id_registry.IdRegistry.new`.

See also: test_iri.py (``iri_segment``), tests/cli/test_cli_id_namespace_root.py
(``id generate --namespace``).
"""

from __future__ import annotations

import pytest

from pitloom.core.iri import require_namespace_iri
from pitloom.id_registry import IdRegistry

_VALID = [
    "https://example.org/ns/demo",
    "https://example.org/ns/demo/",
    "urn:uuid:5a1f7a3c-0b45-4e2a-9d2c-3e4d5f6a7b8c",
    "HTTP://Example.ORG",
    "https://example.org/a%20b?x=y",
    "https://example.org/модель",
    "https://[::1]:8080/ns",
    "x+y.z-1:a",
]

_INVALID = [
    pytest.param("", "empty", id="empty"),
    pytest.param("demo", "scheme", id="bare-word"),
    pytest.param("/ns/demo", "scheme", id="absolute-path"),
    pytest.param("example.org/ns", "scheme", id="no-scheme"),
    pytest.param("1http://x", "scheme", id="digit-scheme"),
    pytest.param("https:", "scheme", id="nothing-after-scheme"),
    pytest.param("https://example.org/ns#", "#", id="empty-fragment"),
    pytest.param("https://example.org/ns#frag", "#", id="fragment"),
    pytest.param("https://example.org/a b", "IRI", id="space"),
    pytest.param("https://example.org/a\nb", "IRI", id="newline"),
    pytest.param("https://example.org/100%", "IRI", id="bare-percent"),
    pytest.param("https://example.org/a%zz", "IRI", id="bad-percent"),
    pytest.param('https://example.org/<a>"', "IRI", id="angle-quote"),
    pytest.param(f"https://example.org/a{chr(0x202E)}", "IRI", id="bidi-control"),
]


@pytest.mark.parametrize("value", _VALID)
def test_require_namespace_iri_accepts_an_absolute_iri(value: str) -> None:
    assert require_namespace_iri(value) == value


@pytest.mark.parametrize(("value", "reason"), _INVALID)
def test_require_namespace_iri_rejects(value: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        require_namespace_iri(value)


def test_registry_new_takes_an_explicit_namespace() -> None:
    explicit = IdRegistry.new("demo", namespace="https://example.org/ns/demo")
    minted = IdRegistry.new("demo")

    assert explicit.namespace == "https://example.org/ns/demo"
    assert minted.namespace.startswith("https://spdx.org/spdxdocs/demo-")
    assert minted.namespace != IdRegistry.new("demo").namespace  # a UUID4 each time


@pytest.mark.parametrize("value", ["", "relative", "https://x.org/ns#"])
def test_registry_new_rejects_an_invalid_namespace(value: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        IdRegistry.new("demo", namespace=value)
