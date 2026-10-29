# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The trust rule on lines nobody printed: forged lines (the PR #390
review's probes among them) are refused, whatever their code, and the
check stays fast on a long hostile line.

See also: tests/messages/test_messages_lines.py (lines Pitloom prints).
"""

from __future__ import annotations

import time

import pytest

from pitloom.messages import (
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LONGEST_LINE,
    Message,
    trusted_message,
)

_OID = "0123456789abcdef" * 4
_POINTER = (
    f"'m.gguf': header is a Git LFS pointer, content not pulled (oid sha256:{_OID}, "
    "size 3 bytes); run 'git lfs pull'"
)
_LOOKS = "header looks like a Git LFS pointer but is not a valid one"

#: Lines Pitloom would print, as (line, entry).
_TRUSTED = [
    (
        "WARNING: FILE=a: Git LFS pointer, content not read (2 files); clone "
        "with git lfs, then run on the directory [lfs-pointer]",
        LFS_POINTER,
    ),
    (
        "WARNING: FILE=x [lfs-pointer]: Git LFS pointer shipped (12 files); the "
        "build did not pull LFS content [lfs-pointer/shipped]",
        LFS_POINTER_SHIPPED,
    ),
    (f"ERROR: {_POINTER} [lfs-pointer]", LFS_POINTER),
    (f"ERROR: model command failed: {_POINTER} [lfs-pointer]", LFS_POINTER),
    (
        f'ERROR: SBOM generation failed: "it\'s.gguf": {_LOOKS} '
        "[lfs-pointer-malformed]",
        LFS_POINTER_MALFORMED,
    ),
    (
        f"WARNING: FORMAT=gguf FILE=src/m.gguf: {_LOOKS}; not listed as an AI "
        "model [lfs-pointer-malformed]",
        LFS_POINTER_MALFORMED,
    ),
    (
        f"WARNING: FILE=src/m.bin: {_LOOKS}; not listed as an AI model "
        "[lfs-pointer-malformed]",
        LFS_POINTER_MALFORMED,
    ),
]

#: Lines no surface prints, each with a catalogued code at its end.
_FORGED = [
    # the review's probes: any text before an ERROR shape, a stray frame
    f"ERROR: anything at all, even WARNING: text: {_LOOKS} [lfs-pointer-malformed]",
    f"ERROR: anything at all, even WARNING: 'text': {_LOOKS} [lfs-pointer-malformed]",
    "ERROR: SBOM generation failed: project directory not found: x: "
    f"{_LOOKS} [lfs-pointer-malformed]",
    f"ERROR: model command failed: model command failed: {_POINTER} [lfs-pointer]",
    # values that do not have their field's shape
    "ERROR: x: header is a Git LFS pointer, content not pulled (oid sha256:zz, "
    "size lots); run 'git lfs pull' [lfs-pointer]",
    _POINTER.replace("3 bytes", "lots").join(["ERROR: ", " [lfs-pointer]"]),
    _POINTER.replace(_OID, "ab").join(["ERROR: ", " [lfs-pointer]"]),
    "WARNING: FILE=a: Git LFS pointer, content not read (1 files); run 'git lfs "
    "pull' for the content [lfs-pointer]",
    f"WARNING: FORMAT=Evil; x FILE=a: {_LOOKS}; not listed as an AI model "
    "[lfs-pointer-malformed]",
    # two actions run together
    "WARNING: FILE=a: Git LFS pointer, content not read; run 'git lfs pull' for "
    "the content; clone with git lfs, then run on the directory [lfs-pointer]",
    # a shape at a level it is not printed at
    f"WARNING: 'm.gguf': {_LOOKS} [lfs-pointer-malformed]",
    f"WARNING: {_POINTER} [lfs-pointer]",
    "ERROR: FILE=a: Git LFS pointer, content not read; run 'git lfs pull' for "
    "the content [lfs-pointer]",
    "INFO: FILE=a: Git LFS pointer shipped; the build did not pull LFS content "
    "[lfs-pointer/shipped]",
    # another entry's shape, and the old wording of the malformed line
    f"WARNING: FILE=src/m.bin: {_LOOKS}; not listed as an AI model [lfs-pointer]",
    "ERROR: 'm.gguf': header is a Git LFS pointer [lfs-pointer-malformed]",
    # a hostile file name at the end of a line no entry says
    "WARNING: not listed: x [lfs-pointer]",
]


@pytest.mark.parametrize(("line", "entry"), _TRUSTED, ids=lambda v: str(v)[:30])
def test_a_line_pitloom_prints_is_trusted(line: str, entry: Message) -> None:
    assert trusted_message(line) is entry


@pytest.mark.parametrize("line", _FORGED, ids=lambda v: v[:40])
def test_a_forged_line_is_not_trusted(line: str) -> None:
    assert trusted_message(line) is None


@pytest.mark.parametrize(
    "body",
    [
        "FILE=" + ": Git LFS pointer, content not read" * 470,
        "FORMAT=gguf FILE=" + "x: FILE=a: header looks like" * 600,
        "model command failed: " + "'x': header is a Git LFS pointer" * 500,
    ],
    ids=["prefix", "relay", "frame"],
)
def test_a_long_hostile_line_is_refused_quickly(body: str) -> None:
    """About 16,000 characters that match a shape's start but never its end:
    the regular expressions do not backtrack without bound."""
    start = time.monotonic()
    for code in ("lfs-pointer", "lfs-pointer-malformed"):
        for level in ("WARNING", "ERROR"):
            assert trusted_message(f"{level}: {body} [{code}]") is None
    assert time.monotonic() - start < 2.0


def test_a_line_up_to_the_longest_is_read_back() -> None:
    """A real line padded by its file name to exactly :data:`LONGEST_LINE`
    characters is trusted; one character more is not."""
    tail = ": Git LFS pointer shipped; the build did not pull LFS content"
    head, end = "WARNING: FILE=", f"{tail} [lfs-pointer/shipped]"
    line = head + "a" * (LONGEST_LINE - len(head) - len(end)) + end
    assert len(line) == LONGEST_LINE
    assert trusted_message(line) is LFS_POINTER_SHIPPED
    assert trusted_message(head + "a" + line[len(head) :]) is None
