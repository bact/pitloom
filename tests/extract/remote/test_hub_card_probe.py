# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A downloaded Hub card is third-party text, and the loaders of the model
card and the dataset card no longer wrap :func:`pitloom.enrich.readme.read_card`
in a broad ``except``: the reader must never raise on an unreadable file or a
hostile one. This probe lists the inputs relied on (a directory, a file
without read permission, non-UTF-8 bytes, a byte-order mark before the
frontmatter, an unclosed frontmatter past the cap, invalid YAML, a date that
does not exist, nesting past the recursion limit): each is read by both
loaders, gives its result and says at most one coded ``WARNING:``. A failure of
the reader that is no such input (a bug, an
:class:`~pitloom.core.internal_error.InternalError`) is not turned into a
warning.

See also: tests/messages/test_card_malformed.py (the reader's warnings),
tests/extract/remote/test_huggingface_dataset_names.py (the card warnings of
a dataset) and tests/extract/remote/test_huggingface_fetch.py (the model
card).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.enrich.readme import MODEL_CARD_MAX_BYTES
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from pitloom.extract.remote import huggingface_fetch as hub_fetch
from pitloom.extract.remote.huggingface_dataset import _load_dataset_card
from pitloom.extract.remote.huggingface_fetch import _load_model_card
from pitloom.logging_config import CODE_ATTR
from tests._unreadable import deny
from tests.extract.remote.hf_patches._hf_patches_base import fake_hub

pytestmark = pytest.mark.platform  # permissions, directories, encodings

_SHA = "89abcdef0123456789abcdef0123456789abcdef"

if TYPE_CHECKING:
    _Loader = Callable[[Any, str, str | None], tuple[str | None, dict[str, Any]]]

# Short-circuited: os.geteuid does not exist on Windows.
_CHMOD_WORKS = sys.platform != "win32" and os.geteuid() != 0

_LOADERS: list[Any] = [
    pytest.param(_load_model_card, id="model-card"),
    pytest.param(_load_dataset_card, id="dataset-card"),
]

_FRONT = b"---\nlicense: mit\n---\n"

#: name -> (the file's bytes, whether a card is read, the frontmatter read
#: (``None``: it is not), the code said, ``None`` for silence).
_FILES: dict[str, tuple[bytes, bool, dict[str, Any] | None, str | None]] = {
    "non-utf8": (_FRONT + b"\xff\xfe bad", True, {"license": "mit"}, None),
    "bom": (b"\xef\xbb\xbf" + _FRONT + b"Text.", True, {"license": "mit"}, None),
    "unclosed": (
        b"---\nlicense: mit\n" + b"x" * (MODEL_CARD_MAX_BYTES + 10),
        False,
        None,
        "over-cap",
    ),
    "invalid-yaml": (b"---\nlicense: [unclosed\n---\nx", True, None, "card-malformed"),
    "impossible-date": (b"---\ndate: 2024-02-30\n---\nx", True, None, "card-malformed"),
    "deep-nesting": (
        b"---\nx: " + b"[" * 5000 + b"]" * 5000 + b"\n---\nx",
        True,
        None,
        "card-malformed",
    ),
}


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("loader", _LOADERS)
@pytest.mark.parametrize("name", sorted(_FILES))
def test_a_hostile_card_never_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: _Loader, name: str
) -> None:
    body, has_card, frontmatter, code = _FILES[name]
    card = tmp_path / "README.md"
    card.write_bytes(body)
    text, data = loader(fake_hub(card), "o/m", _SHA)
    warnings = _warnings(caplog)
    if has_card:
        assert text is not None and text.startswith("---")  # a BOM is dropped
        assert data == (frontmatter or {})
    else:
        assert (text, data) == (None, {})
    assert [getattr(r, CODE_ATTR) for r in warnings] == ([code] if code else [])
    assert all("\n" not in r.getMessage() for r in warnings)


def test_non_utf8_bytes_are_read_with_a_replacement_character(tmp_path: Path) -> None:
    card = tmp_path / "README.md"
    card.write_bytes(_FILES["non-utf8"][0])
    text, _data = _load_model_card(fake_hub(card), "o/m", _SHA)
    assert text is not None and "\ufffd" in text and "bad" in text


@pytest.mark.parametrize("loader", _LOADERS)
def test_a_directory_in_place_of_the_card_is_one_warning_and_no_card(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, loader: _Loader
) -> None:
    directory = tmp_path / "README.md"
    directory.mkdir()
    assert loader(fake_hub(directory), "o/m", _SHA) == (None, {})
    (warning,) = _warnings(caplog)
    assert getattr(warning, CODE_ATTR) == "file-unreadable"
    assert str(tmp_path) not in warning.getMessage()


@pytest.mark.parametrize("loader", _LOADERS)
@pytest.mark.parametrize(
    "mode",
    ["open", pytest.param("chmod-file", marks=pytest.mark.skipif(
        not _CHMOD_WORKS, reason="needs POSIX permissions, non-root"))],
    ids=["open-denied", "mode-0"],
)  # fmt: skip
def test_a_card_without_read_permission_is_one_warning_and_no_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    loader: _Loader,
    mode: str,
) -> None:
    card = tmp_path / "README.md"
    card.write_bytes(_FRONT)
    with deny(card, mode, monkeypatch):
        assert loader(fake_hub(card), "o/m", _SHA) == (None, {})
    (warning,) = _warnings(caplog)
    assert getattr(warning, CODE_ATTR) == "file-unreadable"
    assert str(tmp_path) not in warning.getMessage()


# -- no broad ``except``: what is no card's fault is not said as one ----------


@pytest.mark.parametrize(
    ("module", "loader"),
    [(hub_fetch, _load_model_card), (hub_dataset, _load_dataset_card)],
    ids=["model-card", "dataset-card"],
)
@pytest.mark.parametrize(
    "error",
    [InternalError("contract broken"), RuntimeError("a bug")],
    ids=["internal-error", "runtime-error"],
)
def test_a_failure_of_the_reader_is_not_turned_into_a_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    module: Any,
    loader: _Loader,
    error: Exception,
) -> None:
    card = tmp_path / "README.md"
    card.write_bytes(_FRONT)
    with patch.object(module, "read_card", side_effect=error):
        with pytest.raises(type(error)) as raised:
            loader(fake_hub(card), "o/m", _SHA)
    assert raised.value is error
    assert not _warnings(caplog)
