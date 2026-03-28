# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for RFC 8785 (JSON Canonicalization Scheme) compliance.

RFC 8785 requires:
  - Object members sorted by key in Unicode code point (UTF-16) order.
  - No extra whitespace outside string values.
  - Numbers in IEEE 754 double-precision form (no trailing zeros, etc.).
  - Array element order is preserved unchanged.

References:
  - RFC 8785: https://www.rfc-editor.org/rfc/rfc8785
  - SPDX 3 canonical serialization:
    https://spdx.github.io/spdx-spec/v3.0.1/serializations/#canonical-serialization
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import rfc8785

from pitloom.assemble import generate_sbom
from pitloom.core.creation import CreationMetadata

# Fixed creation timestamp so every test call with the same pyproject produces
# identical output.  Without this, datetime.now() makes two successive calls
# non-deterministic.
_FIXED_CI = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

_PYPROJECT = """\
[project]
name = "jcs-test"
version = "1.0.0"
description = "RFC 8785 compliance test package"
dependencies = ["requests>=2.28.0"]
"""


def _sbom_compact(tmppath: Path) -> str:
    return generate_sbom(tmppath, creation_info=_FIXED_CI)


def _sbom_pretty(tmppath: Path) -> str:
    return generate_sbom(tmppath, creation_info=_FIXED_CI, pretty=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _keys_sorted_recursive(obj: Any, path: str = "") -> list[str]:
    """Return a list of violation messages where object keys are not sorted."""
    violations: list[str] = []
    if isinstance(obj, dict):
        keys = list(obj.keys())
        if keys != sorted(keys):
            violations.append(
                f"Keys not in lexicographic order at {path!r}: {keys}"
            )
        for k, v in obj.items():
            violations.extend(_keys_sorted_recursive(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_keys_sorted_recursive(item, f"{path}[{i}]"))
    return violations


# ---------------------------------------------------------------------------
# RFC 8785 compliance: compact output
# ---------------------------------------------------------------------------


def test_compact_output_equals_rfc8785_canonical() -> None:
    """Compact output must be byte-for-byte equal to rfc8785.dumps() applied
    to the same data structure.

    This is the definitive JCS compliance test: if it passes, the output
    satisfies all RFC 8785 requirements simultaneously (key ordering,
    whitespace, number representation).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        output = _sbom_compact(tmppath)
        data = json.loads(output)
        expected = rfc8785.dumps(data).decode("utf-8")

        assert output == expected, (
            "Compact output is not RFC 8785 canonical.\n"
            f"First divergence: output[{_first_diff(output, expected)}]"
        )


def test_compact_output_keys_sorted_at_every_level() -> None:
    """Every JSON object in the compact output must have its keys in
    lexicographic (Unicode code point) order, including nested objects
    inside @graph elements.

    RFC 8785 §3.2.3 requires members to be sorted by key using UTF-16 code
    units as unsigned integers.  For the ASCII-only keys used in SPDX 3
    JSON-LD this is equivalent to standard lexicographic ordering.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        data = json.loads(_sbom_compact(tmppath))
        violations = _keys_sorted_recursive(data)

        assert not violations, "\n".join(violations)


def test_compact_output_has_no_extra_whitespace() -> None:
    """Compact output must contain no whitespace outside string values.

    RFC 8785 §3.2 prohibits insignificant whitespace (spaces, newlines,
    tabs between tokens).  The round-trip test already covers this
    implicitly; this test makes the constraint explicit and pinpoints which
    character is at fault.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        output = _sbom_compact(tmppath)

        # Walk the token stream via json.JSONDecoder to find whitespace
        # outside string values.  A simpler proxy: verify the output
        # re-encodes with separators=(",", ":") to the same string.
        re_encoded = json.dumps(json.loads(output), separators=(",", ":"))
        # rfc8785 sorts keys; json.dumps without sort_keys does not —
        # compare lengths only to confirm no extra characters were added.
        assert len(output) == len(re_encoded), (
            f"Output length {len(output)} differs from compact re-encode "
            f"length {len(re_encoded)}, suggesting extra whitespace."
        )

        # Directly check for the most common forms of insignificant whitespace.
        assert not output.startswith(" "), "Leading whitespace found"
        assert not output.endswith((" ", "\n", "\r", "\t")), (
            "Trailing whitespace found"
        )


def test_compact_output_graph_array_order_preserved() -> None:
    """RFC 8785 §3.2.2 requires that array element order is not changed.

    The @graph array is pre-sorted by _graph_sort_key before rfc8785.dumps()
    is applied.  This test verifies that rfc8785 does not disturb the
    intended element order.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        output = _sbom_compact(tmppath)
        data = json.loads(output)

        graph = data["@graph"]
        types = [e["type"] for e in graph]

        # Priority order must be intact after rfc8785 serialization.
        assert types[0] == "CreationInfo", (
            "rfc8785 must not reorder @graph: CreationInfo must be first"
        )
        assert "SpdxDocument" in types
        spdx_doc_idx = types.index("SpdxDocument")
        assert types[0] == "CreationInfo"
        assert spdx_doc_idx > 0, "SpdxDocument must follow CreationInfo"


# ---------------------------------------------------------------------------
# RFC 8785 compliance: pretty output
# ---------------------------------------------------------------------------


def test_pretty_output_keys_sorted() -> None:
    """Pretty output (pretty=True) must also have keys sorted.

    Pretty mode uses json.dumps(sort_keys=True) which satisfies the key
    ordering requirement.  It is NOT full JCS (it has indentation), but
    sorted keys make diffs more readable and comparisons more predictable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        output = _sbom_pretty(tmppath)
        data = json.loads(output)
        violations = _keys_sorted_recursive(data)

        assert not violations, "\n".join(violations)


def test_pretty_output_is_not_jcs_canonical() -> None:
    """Pretty output must differ from the JCS canonical form.

    This test acts as a contract: pretty=True is intentionally NOT JCS
    (it has indentation for readability).  If this ever accidentally
    becomes equal, something has changed that needs a deliberate decision.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / "pyproject.toml").write_text(_PYPROJECT)

        pretty = _sbom_pretty(tmppath)
        canonical = rfc8785.dumps(json.loads(pretty)).decode("utf-8")

        assert pretty != canonical, (
            "Pretty output should not be JCS canonical (it has indentation)"
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _first_diff(a: str, b: str) -> int:
    """Return the index of the first character where strings a and b differ."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return min(len(a), len(b))
