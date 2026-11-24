# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The scanner's messages name a model by its stable path: the temporary
copy a reader was handed is removed from an exception's text in every
spelling the text may quote it in, a library's own cause is what is said, and
a whole Git LFS pointer is told apart from the files that are not one.

See also: :mod:`tests.extract.scanner.test_scanner_reader_logs`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import os
from contextlib import nullcontext
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.lfs_pointer import LfsPointer
from pitloom.extract._scanner_messages import (
    say_not_a_model,
    say_unread,
    scrub,
)
from pitloom.extract.ai_model import LFS_POINTER_REASON, NotAModel
from pitloom.extract.scanner import ModelCandidate, scan_step
from pitloom.logging_config import CODE_ATTR

pytestmark = pytest.mark.platform

_POSIX = os.name == "posix"
_LOG = logging.getLogger("pitloom.test_scanner_messages_paths")
_STABLE = "demo/m.gguf"
#: A combining mark that is printable, so ``repr`` keeps it, and in
#: :data:`~pitloom.core.untrusted_text.DISPLAY_CONTROLS`, so the text escapes it.
_MARK = "\u034f"


def _candidate(physical: str = _STABLE, pointer: object = None) -> ModelCandidate:
    return ModelCandidate(
        distribution_path="m.gguf",
        physical_path=physical,
        sniff=lambda: b"",
        materialize=nullcontext,  # type: ignore[arg-type]
        pointer=pointer,  # type: ignore[arg-type]
    )


@pytest.mark.skipif(not _POSIX, reason="a POSIX path spelling")
@pytest.mark.parametrize(
    "text",
    ['cannot open {} "x"', "cannot open {}"],
    ids=["quote-and-mark-in-a-single-quoted-text", "mark-in-a-double-quoted-text"],
)
def test_a_temp_path_with_a_quote_and_a_control_is_removed(
    tmp_path: Path, text: str
) -> None:
    """The text is escaped as a literal; a quote in the path is escaped as
    that literal's delimiter needs, or not."""
    path = tmp_path / f"a'b{_MARK}c" / "m.gguf"
    out = scrub(text.format(path), path, _STABLE)
    assert _STABLE in out
    assert os.path.realpath(tmp_path) not in out
    assert str(tmp_path) not in out


@pytest.mark.skipif(not _POSIX, reason="a POSIX path spelling")
def test_a_real_path_is_removed_in_its_escaped_spelling(tmp_path: Path) -> None:
    """A reader quotes the file it opened: the symlink's target."""
    target = tmp_path / f"a{_MARK}b"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available")
    path = link / "m.gguf"
    real = os.path.realpath(path)
    assert real != str(path)  # the setup took effect
    out = scrub(f"cannot open {real}", path, _STABLE)
    assert _STABLE in out
    assert os.path.realpath(tmp_path) not in out


def _error(exc: Exception, caplog: pytest.LogCaptureFixture, path: Path) -> str:
    candidate = _candidate()
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        say_unread(_LOG, AiModelFormat.GGUF, candidate, exc, path)
    (record,) = caplog.records
    return record.getMessage()


def _coded(message: str, cause: BaseException | None) -> ImportError:
    exc = ImportError(message)
    setattr(exc, CODE_ATTR, "library-unusable")
    exc.__cause__ = cause
    return exc


@pytest.mark.parametrize(
    ("cause", "said", "unsaid"),
    [
        (ImportError("inner reason"), "inner reason", "outer"),
        (None, "outer", "inner"),
    ],
    ids=["cause", "no-cause"],
)
def test_a_coded_import_error_says_its_cause(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    cause: ImportError | None,
    said: str,
    unsaid: str,
) -> None:
    """What the import reported is the cause; the error itself when it has none."""
    line = _error(_coded("outer text", cause), caplog, tmp_path / "0.gguf")
    assert said in line and unsaid not in line


@pytest.mark.parametrize("coded", [True, False], ids=["library", "reader"])
def test_the_temp_copy_is_not_named_in_what_is_said(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, coded: bool
) -> None:
    copy = tmp_path / "0.gguf"
    cause = RuntimeError(f"bad header in {copy}")
    exc: Exception = _coded("outer", cause) if coded else cause
    line = _error(exc, caplog, copy)
    assert f"bad header in {_STABLE}" in line
    assert str(tmp_path) not in line


def _pointer() -> LfsPointer:
    return LfsPointer(oid="0" * 64, size=1)


_GGUF, _NONE = AiModelFormat.GGUF, None


@pytest.mark.parametrize(
    ("fmt", "candidate", "reason", "whole"),
    [
        (_GGUF, _candidate(pointer=_pointer), LFS_POINTER_REASON, True),
        (_GGUF, _candidate(pointer=lambda: None), LFS_POINTER_REASON, False),
        (_GGUF, _candidate(), LFS_POINTER_REASON, False),
        (_GGUF, _candidate(pointer=_pointer), "header is not gguf", False),
        (_NONE, _candidate(pointer=_pointer), LFS_POINTER_REASON, True),
        (_NONE, _candidate(pointer=lambda: None), LFS_POINTER_REASON, False),
    ],
    ids=["whole", "malformed", "unknown", "other-format", "whole-bin", "malformed-bin"],
)
def test_only_a_whole_valid_pointer_is_told_apart(
    fmt: AiModelFormat | None, candidate: ModelCandidate, reason: str, whole: bool
) -> None:
    refusal = NotAModel(fmt, reason)
    assert say_not_a_model(_LOG, refusal, candidate) is whole
    pointers: list[str] = []

    def step(_candidate: ModelCandidate) -> None:
        raise refusal

    assert scan_step(candidate, step, pointers) is None
    assert pointers == ([_STABLE] if whole else [])


def test_a_pointer_debug_line_is_one_line(caplog: pytest.LogCaptureFixture) -> None:
    candidate = _candidate("d/a\nb.gguf", pointer=_pointer)
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        say_not_a_model(
            _LOG, NotAModel(AiModelFormat.GGUF, LFS_POINTER_REASON), candidate
        )
    (record,) = caplog.records
    assert "\n" not in record.getMessage()
    assert "a\\nb.gguf" in record.getMessage()
