# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift-guard: every ``--build-timeout``/``build-timeout:`` example shown
in shipped docs and skills must actually parse with
:func:`pitloom.core._models_wheel_types.parse_build_timeout`.

Skills/docs have no test suite of their own (see CLAUDE.md's "Usage
surfaces"), so a duration-grammar change that silently invalidates a
copy-paste example would otherwise only be caught by hand. If a case
here fails, fix the doc's example, not the parser -- unless the parser
itself is wrong, in which case fix both together.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pitloom.core._models_wheel_types import parse_build_timeout

REPO_ROOT = Path(__file__).resolve().parents[1]

# Doc metavars, never a real duration value.
_PLACEHOLDERS = frozenset({"DURATION", "SECONDS"})

_SCAN_GLOBS = (
    "skills/**/*.md",
    "docs/*.md",
    "README.md",
    "action.yml",
    ".github/workflows/action-selftest.yml",
)

_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_SPAN_RE = re.compile(r"`([^`\n]+)`")
_FLAG_RE = re.compile(r"--build-timeout\s+(\S+)")
_INPUT_RE = re.compile(r'build-timeout:\s*"([^"]*)"')
_TRAILING_PUNCTUATION = ").,;:]}"


def _strip_trailing_punctuation(token: str) -> str:
    return token.rstrip(_TRAILING_PUNCTUATION)


def _code_snippets(text: str, *, whole_file: bool) -> list[str]:
    """Markdown: only fenced code blocks and inline code spans, so prose
    that merely *names* the flag (with no value following it) is never
    mistaken for a usage example. YAML (``action.yml``) has no code-span
    concept, so it's scanned whole."""
    if whole_file:
        return [text]
    return _FENCE_RE.findall(text) + _SPAN_RE.findall(text)


def _find_examples(path: Path) -> list[tuple[str, str]]:
    """Return ``(kind, value)`` pairs found in *path* -- ``kind`` is
    ``"flag"`` for ``--build-timeout <value>`` or ``"input"`` for
    ``build-timeout: "<value>"`` (the GitHub Action input form)."""
    text = path.read_text(encoding="utf-8")
    whole_file = path.suffix in {".yml", ".yaml"}
    found: list[tuple[str, str]] = []
    for snippet in _code_snippets(text, whole_file=whole_file):
        for flag_match in _FLAG_RE.finditer(snippet):
            value = _strip_trailing_punctuation(flag_match.group(1))
            found.append(("flag", value))
        for input_match in _INPUT_RE.finditer(snippet):
            found.append(("input", input_match.group(1)))
    return found


def _collect_cases() -> list[tuple[str, str, str]]:
    """``(file-relative-posix-path, kind, value)`` for every scanned file,
    across every glob in :data:`_SCAN_GLOBS`."""
    cases: list[tuple[str, str, str]] = []
    for pattern in _SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            cases.extend((rel, kind, value) for kind, value in _find_examples(path))
    return cases


_CASES = _collect_cases()


def _case_id(case: tuple[str, str, str]) -> str:
    rel, kind, value = case
    return f"{rel}:{kind}:{value}"


def test_found_at_least_one_example_under_sbom_generate() -> None:
    """Guard against a vacuous scan: if the ``sbom-generate`` skill's own
    docs stop showing a ``--build-timeout`` example, fail loudly here
    instead of the parametrized test below silently having zero cases."""
    assert any(rel.startswith("skills/sbom-generate/") for rel, _kind, _value in _CASES)


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_documented_build_timeout_example_parses(case: tuple[str, str, str]) -> None:
    _rel, _kind, value = case
    if value in _PLACEHOLDERS:
        pytest.skip(f"placeholder value {value!r}, not a real duration example")
    assert parse_build_timeout(value) >= 1
