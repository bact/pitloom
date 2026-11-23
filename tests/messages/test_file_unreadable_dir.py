# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``file-unreadable``'s directory line: a loom dataset directory whose card
could not be read for a reason that names no file of it. The card reader
says each problem of the card itself (``card-malformed``,
``file-unreadable``, ``dir-unlistable``, ``over-cap``); only what escapes
it reaches the dataset's own safety net (``file-unreadable``'s directory
line). A current directory removed while the run lasts no longer does:
the card is read, labelled by its bare name.

See also: :func:`pitloom._loom_dataset_meta.read_sources`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom._loom_dataset_meta import read_sources
from pitloom.messages import trusted_message

pytestmark = pytest.mark.platform

_CODE = "file-unreadable"
_SECRET = "s3cr3t-value"


def _dataset(root: Path) -> Path:
    path = root / "corpus"
    path.mkdir()
    (path / "README.md").write_bytes(b"---\nlicense: mit\n---\n")
    return path


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot remove the cwd")
def test_a_removed_current_directory_still_reads_the_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The label is relative to the current directory: with that gone, an
    absolute dataset directory's card is still read, labelled by its bare
    name, and nothing is warned."""
    dataset = _dataset(tmp_path)
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    with pytest.raises(FileNotFoundError):
        os.getcwd()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        sources = read_sources(
            str(dataset), croissant=None, declared_license="MIT", caller_info="x"
        )
    monkeypatch.chdir(tmp_path)
    assert not _warnings(caplog)
    (card,) = sources.read
    assert card.license == "mit"
    assert all("gone" not in str(value) for value in card.provenance.values())
    assert any("corpus" in str(value) for value in card.provenance.values())


_HOSTILE = {
    "newline-forged-line": "a\nWARNING: forged [config-invalid]",
    "ansi": "\x1b[31mred",
    "url-credential": f"see https://user:{_SECRET}@h.example/x",
    "huge": "y" * 1_000_000,
}


@pytest.mark.parametrize("failure", _HOSTILE.values(), ids=_HOSTILE.keys())
def test_what_escapes_the_reader_is_one_masked_cut_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    """An exception's text is not ours: on one line, a credential masked,
    cut, escaped; the code read back is ours."""
    monkeypatch.chdir(tmp_path)
    _dataset(tmp_path)
    with (
        caplog.at_level(logging.WARNING, logger="pitloom"),
        patch(
            "pitloom._loom_dataset_meta.read_dataset_card",
            side_effect=RuntimeError(failure),
        ),
    ):
        read_sources("corpus", croissant=None, declared_license=None, caller_info="x")
    (record,) = _warnings(caplog)
    text = record.getMessage()
    assert text.startswith("DIR=corpus: could not read for the dataset card; ")
    assert "\n" not in text and "\x1b" not in text and _SECRET not in text
    assert len(text) < 1_000
    line = f"WARNING: {text} [{_CODE}]"
    trusted = trusted_message(line)
    assert trusted is not None and trusted.code == _CODE
