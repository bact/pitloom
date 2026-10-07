# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared scan of the user-facing Markdown: fenced blocks and inline code.

Used by :mod:`tests.test_docs_examples` (do the examples still run against the
current API) and :mod:`tests.test_docs_links` (do the links still resolve).
Nothing here imports Pitloom.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The user manual: the README and every page of the docs site.
DOC_FILES: tuple[Path, ...] = (
    REPO_ROOT / "README.md",
    *sorted((REPO_ROOT / "docs").glob("*.md")),
)

#: Every Markdown file that shows a ``loom`` command to a user.
CLI_DOC_FILES: tuple[Path, ...] = (
    *DOC_FILES,
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "examples" / "sentimentdemo-aibom" / "README.md",
    *sorted((REPO_ROOT / "skills").rglob("*.md")),
)

_FENCE_RE = re.compile(
    r"^[ \t]*```(?P<lang>\w*)[^\n]*\n(?P<body>.*?)^[ \t]*```", re.DOTALL | re.MULTILINE
)
_INLINE_RE = re.compile(r"`([^`\n]+)`")


@dataclass(frozen=True)
class Snippet:
    """One block of code in a Markdown file."""

    path: str  #: Repository-relative POSIX path of the file.
    line: int  #: 1-based line of the block's first line of content.
    lang: str  #: The fence's language tag, ``""`` for an inline span.
    body: str  #: The code, dedented.

    @property
    def ident(self) -> str:
        """A short test id: ``docs/cli.md:61``."""
        return f"{self.path}:{self.line}"


def rel(path: Path) -> str:
    """The repository-relative POSIX path of *path*."""
    return path.relative_to(REPO_ROOT).as_posix()


def read(path: Path) -> str:
    """The text of *path*, UTF-8."""
    return path.read_text(encoding="utf-8")


def fenced_blocks(path: Path) -> list[Snippet]:
    """Every fenced code block of *path*, in file order."""
    text = read(path)
    return [
        Snippet(
            rel(path),
            text.count("\n", 0, m.start("body")) + 1,
            m.group("lang"),
            textwrap.dedent(m.group("body")),
        )
        for m in _FENCE_RE.finditer(text)
    ]


def inline_spans(path: Path) -> list[Snippet]:
    """Every inline code span of *path* outside a fenced block."""
    text = without_fences(path)
    return [
        Snippet(rel(path), text.count("\n", 0, m.start()) + 1, "", m.group(1))
        for m in _INLINE_RE.finditer(text)
    ]


def without_fences(path: Path) -> str:
    """The text of *path* with fenced blocks blanked out, keeping every line
    number. Headings keep their inline code."""
    return _FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), read(path))


def prose(path: Path) -> str:
    """The text of *path* with fenced blocks and inline code blanked out,
    keeping every line number."""
    return _INLINE_RE.sub("", without_fences(path))
