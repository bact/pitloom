# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for the low-level pitloom.extract.remote.huggingface_fetch
helpers -- the raw HF Hub I/O functions.

These bypass the full ``read_huggingface()`` pipeline (exercised by the
sibling ``test_huggingface_*.py`` modules) to reach branches that the
higher-level facade never exercises: the success paths of the raw fetch
helpers and their failures.

See also: tests/extract/remote/test_card_description.py (the card
description), the topic-grouped hf_patches/_hf_patches_*.py submodules for the
shared mock-HF-API helpers used by the higher-level tests.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import create_autospec, patch

import pytest
from huggingface_hub.hf_api import ModelInfo

from pitloom.enrich.readme import MODEL_CARD_CAP
from pitloom.extract._license_text_match import LicenseTextReading
from pitloom.extract.remote._card_description import card_description
from pitloom.extract.remote._hub_files import HUB_JSON_CAP, FileKind, HubFiles
from pitloom.extract.remote.huggingface_fetch import (
    MODEL_INFO_OUTCOME,
    _detect_license_from_hf_files,
    _fetch_all_hf_data,
    _license_files_in,
    _load_model_card,
    _load_model_info,
    _resolve_license,
    _safe_load_json,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.network import DOWNLOAD_FAILED

_LOGGER_NAME = "pitloom.extract.remote.huggingface_fetch"


def _hub(path: Path | None = None) -> Any:
    """A :class:`HubFiles` whose every read gives *path* (``None``: the
    repository does not hold the file)."""
    hub = create_autospec(HubFiles, instance=True)
    hub.asks_hub = True
    hub.read.return_value = path
    return hub


def _model_info(**api_json: Any) -> ModelInfo:
    """A real ``ModelInfo`` built from the Hub's JSON keys (``id`` filled in).

    Its ``__init__`` is untyped in some ``huggingface_hub`` versions: call it
    through ``Any``, which is not an error in the typed ones either."""
    build: Any = ModelInfo
    info: ModelInfo = build(**{"id": "org/model", **api_json})
    return info


# ---------------------------------------------------------------------------
# _safe_load_json
# ---------------------------------------------------------------------------


def test_safe_load_json_with_pinned_revision_succeeds_without_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The download at a pinned revision and the parse succeed, returning
    the parsed JSON dict, with no warning."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"model_type": "mistral"}), encoding="utf-8")

    hub = _hub(config_file)
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = _safe_load_json(hub, "org/model", "config.json", revision="deadbeef")
    hub.read.assert_called_once_with(
        "org/model",
        "config.json",
        revision="deadbeef",
        kind=FileKind(HUB_JSON_CAP, "config.json not read"),
    )

    assert result == {"model_type": "mistral"}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_safe_load_json_without_revision_says_nothing_itself(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No revision: the file is read all the same, and the reader says
    nothing of it (the unpinned model is said once, where the revision is
    decided)."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"a": 1}), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        result = _safe_load_json(_hub(config_file), "org/model", "config.json")

    assert result == {"a": 1}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# _load_model_card
# ---------------------------------------------------------------------------


def _card(tmp_path: Path, text: bytes) -> tuple[str | None, dict[str, Any]]:
    """:func:`_load_model_card` of a downloaded card holding *text*."""
    card = tmp_path / "README.md"
    card.write_bytes(text)
    hub = _hub(card)
    got = _load_model_card(hub, "org/model", "1")
    hub.read.assert_called_once_with(
        "org/model",
        "README.md",
        revision="1",
        kind=FileKind(MODEL_CARD_CAP, "model card not read"),
    )
    return got


def test_load_model_card_returns_the_whole_card_so_a_description_is_found(
    tmp_path: Path,
) -> None:
    """The whole card, front matter included, as the file holds it (a BOM
    dropped); the description helper still finds a description."""
    raw = b"\xef\xbb\xbf---\nlicense: mit\n---\n\n# Title\n\nA small test model.\n"
    text, data = _card(tmp_path, raw)
    assert text is not None and text == raw[3:].decode()
    assert data == {"license": "mit"}
    assert card_description(text) == "A small test model."


@pytest.mark.parametrize(
    ("raw", "data"),
    [
        (b"", {}),
        (b"# Card\n", {}),
        (b"---\n- a list\n---\nx\n", {}),
        (b"---\ntags: one\n---\n", {"tags": ["one"]}),
        (b"---\ntags: [a, b, a, 3, 3]\n---\n", {"tags": ["a", "b", 3]}),
        (b"---\ntags: {a: 1}\n---\n", {"tags": {"a": 1}}),
        # As the file states it: ``huggingface_hub``'s card data rebuilt the
        # model-index (and refused the whole card for a malformed one).
        (b"---\nmodel-index: [{x: 1}]\n---\n", {"model-index": [{"x": 1}]}),
    ],
    ids=["empty", "no-frontmatter", "no-mapping", "tag", "tags", "odd-tags", "index"],
)
def test_a_model_card_s_frontmatter_is_as_the_file_states_it(
    tmp_path: Path, raw: bytes, data: dict[str, Any]
) -> None:
    text, got = _card(tmp_path, raw)
    assert got == data
    assert text == (raw.decode() or None)


def test_a_model_card_with_malformed_yaml_keeps_its_text(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One ``card-malformed`` ``WARNING:`` naming the model; the card's text
    (and so its description) is kept."""
    text, data = _card(tmp_path, b"---\nlicense: [\n---\n\nA model.\n")
    assert not data and text is not None and card_description(text) == "A model."
    (record,) = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert record.getMessage().startswith(
        "FILE=org/model: model card frontmatter is not valid YAML; "
    )


def test_a_model_card_absent_or_not_fetched_is_empty() -> None:
    assert _load_model_card(_hub(None), "org/model") == (None, {})


# ---------------------------------------------------------------------------
# _load_model_info
# ---------------------------------------------------------------------------


def test_load_model_info_all_fields_present() -> None:
    info = _model_info(
        author="mistralai",
        sha="deadbeef",
        createdAt="2023-09-20T13:03:50.000Z",
        lastModified="2023-09-21T00:00:00.000Z",
        downloads=1234,
        tags=["license:apache-2.0", "region:us"],
        safetensors={"parameters": {"BF16": 5}, "total": 5},
    )
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert result == {
        "author": "mistralai",
        "sha": "deadbeef",
        "created_at": "2023-09-20T13:03:50+00:00",
        "last_modified": "2023-09-21T00:00:00+00:00",
        "downloads": 1234,
        "tags": ["license:apache-2.0", "region:us"],
        "safetensors_total": 5,
    }


def test_load_model_info_falsy_fields_omitted_but_zero_downloads_kept() -> None:
    # author/created_at/last_modified/tags are falsy -> omitted. downloads
    # uses an "is not None" check (not truthiness), so 0 is still recorded.
    info = _model_info(author=None, sha="abc", downloads=0, tags=[])
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert result == {"sha": "abc", "downloads": 0}


def test_load_model_info_sha_and_downloads_none_omitted() -> None:
    # sha and downloads both falsy/None -> both keys omitted, exercising the
    # false branch of each "if" independently of the other falsy fields.
    info = _model_info(author="someone", sha=None, downloads=None, tags=[])
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert "sha" not in result
    assert "downloads" not in result
    assert result == {"author": "someone"}


_ST = {"parameters": {"BF16": 5}, "total": 5}


@pytest.mark.parametrize(
    ("safetensors", "gguf", "expected"),
    [
        (None, None, {}),  # neither: silent
        (_ST, None, {"safetensors_total": 5}),
        # Kept as the Hub sent it: the producer validates it
        ({"parameters": {}, "total": "7"}, None, {"safetensors_total": "7"}),
        ({"parameters": {}, "total": 0}, None, {"safetensors_total": 0}),
        (None, {"total": 9, "architecture": "llama"}, {"gguf_total": 9}),
        (None, {"total": "9"}, {"gguf_total": "9"}),
        (_ST, {"total": 9}, {"safetensors_total": 5}),  # Safetensors wins
        (None, {"architecture": "llama"}, {}),  # no total: silent
        (None, ["total"], {}),  # not a mapping: silent
    ],
    ids=[
        "absent",
        "present",
        "raw-string",
        "zero",
        "gguf",
        "gguf-raw",
        "both",
        "gguf-no-total",
        "gguf-not-dict",
    ],
)
def test_load_model_info_stated_total_kept_raw(
    safetensors: dict[str, Any] | None,
    gguf: Any,
    expected: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    info = _model_info(safetensors=safetensors, gguf=gguf)
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")

    assert result == expected
    assert not caplog.records


# ---------------------------------------------------------------------------
# _license_files_in
# ---------------------------------------------------------------------------


def test_license_files_in_filters_and_orders_by_priority() -> None:
    # _HF_LICENSE_FILENAMES priority: LICENSE, LICENCE, COPYING, NOTICE, ...
    existing = {"COPYING", "LICENSE.txt", "LICENSE", "NOTICE", "docs/LICENSE"}
    assert _license_files_in(existing) == [
        "LICENSE",
        "COPYING",
        "NOTICE",
        "LICENSE.txt",
    ]


@pytest.mark.parametrize(
    ("siblings", "expected"),
    [
        (None, None),
        ([], []),
        ([{"rfilename": "README.md"}, {"rfilename": "a/LICENSE"}], []),
        ([{"rfilename": "NOTICE"}, {"rfilename": "LICENSE"}], ["LICENSE", "NOTICE"]),
    ],
    ids=["no-file-list", "empty-file-list", "none-of-them", "two-in-priority-order"],
)
def test_load_model_info_reads_the_licence_files_from_the_siblings(
    siblings: list[dict[str, str]] | None, expected: list[str] | None
) -> None:
    """Absent (no file list in the response) is not ``[]`` (a list with no
    licence file): the first is unknown, the second is known."""
    info = _model_info(sha="deadbeef", siblings=siblings)
    with patch("huggingface_hub.model_info", return_value=info):
        result = _load_model_info("org/model")
    assert result.get("license_files") == expected
    assert ("license_files" in result) is (expected is not None)


# ---------------------------------------------------------------------------
# _detect_license_from_hf_files
# ---------------------------------------------------------------------------


def test_detect_license_from_hf_files_pinned_revision_detects_license(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A matching licence file yields the detected SPDX ID plus provenance
    # string, with no warning.
    license_file = tmp_path / "LICENSE"
    license_file.write_text("MIT License text...", encoding="utf-8")

    with patch(
        "pitloom.extract._license_text_match.read_license_text",
        return_value=LicenseTextReading("MIT"),
    ):
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            detected_id, provenance = _detect_license_from_hf_files(
                _hub(license_file),
                "org/model",
                revision="deadbeef",
                license_files=["LICENSE"],
            )

    assert detected_id == "MIT"
    assert provenance == (
        "Source: Hugging Face Hub | File: LICENSE | Method: licenseid_detection"
    )
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_detect_license_from_hf_files_undetected_continues_to_next_file(
    tmp_path: Path,
) -> None:
    """When a candidate licence file's text doesn't match any known
    license, the loop continues to the next candidate rather than
    returning immediately -- and falls through to (None, None) once all
    candidates are exhausted."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Some unrecognizable legal text.", encoding="utf-8")

    with patch(
        "pitloom.extract._license_text_match.read_license_text",
        return_value=LicenseTextReading(None),
    ):
        hub = _hub(license_file)
        detected_id, provenance = _detect_license_from_hf_files(
            hub, "org/model", license_files=["LICENSE", "COPYING"]
        )
    assert hub.read.call_count == 2

    assert detected_id is None
    assert provenance is None


_SEVERAL = LicenseTextReading(None, several_texts=True)


@pytest.mark.parametrize(
    ("readings", "expected", "reads"),
    [
        ([_SEVERAL, LicenseTextReading("MIT")], None, 1),  # stops at it
        ([LicenseTextReading(None), LicenseTextReading("MIT")], "MIT", 2),
        ([LicenseTextReading("MIT"), _SEVERAL], "MIT", 1),
    ],
    ids=["several-first", "none-first", "several-second"],
)
def test_a_licence_file_of_several_texts_ends_the_search(
    tmp_path: Path,
    readings: list[LicenseTextReading],
    expected: str | None,
    reads: int,
) -> None:
    """A file holding several licences' texts has no one licence; a later
    file would name only one of them, so it is not read."""
    license_file = tmp_path / "LICENSE"
    license_file.write_text("Licence text.", encoding="utf-8")
    with patch(
        "pitloom.extract._license_text_match.read_license_text",
        side_effect=readings,
    ):
        hub = _hub(license_file)
        detected_id, _ = _detect_license_from_hf_files(
            hub, "org/model", license_files=["LICENSE", "COPYING"]
        )
    assert (detected_id, hub.read.call_count) == (expected, reads)


@pytest.mark.parametrize("files", [None, []], ids=["unknown", "none-held"])
def test_detect_license_from_hf_files_with_no_file_to_read_asks_and_says_nothing(
    files: list[str] | None, caplog: pytest.LogCaptureFixture
) -> None:
    """No file name (the response had no file list, or no licence file in it):
    nothing is downloaded, and nothing is said for a scan that does not
    happen."""
    hub = _hub(None)
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        result = _detect_license_from_hf_files(hub, "org/model", license_files=files)
    assert result == (None, None)
    hub.read.assert_not_called()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("content", "said"),
    [(None, False), (b"{not json", True), (b"[1, 2]", False)],
    ids=["absent", "not-json", "not-an-object"],
)
def test_safe_load_json_without_an_object_returns_none(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    content: bytes | None,
    said: bool,
) -> None:
    """No file (the download warned, or the repository holds none), a file
    that is not JSON (said at ``DEBUG``) or JSON that is no object: ``None``,
    and no ``WARNING:`` of its own."""
    path = None
    if content is not None:
        path = tmp_path / "config.json"
        path.write_bytes(content)
    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        result = _safe_load_json(_hub(path), "org/model", "config.json", "1")
    assert result is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("config.json" in r.getMessage() for r in caplog.records) is said


def test_load_model_card_failure_logs_and_returns_empty(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A card that cannot be read (a directory here): one ``WARNING:``
    naming the model, not the temporary path."""
    text, data = _load_model_card(_hub(tmp_path), "org/model")
    assert (text, data) == (None, {})
    (record,) = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert "FILE=org/model" in record.getMessage()
    assert str(tmp_path) not in record.getMessage()


def test_load_model_info_failure_logs_and_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One coded ``WARNING:`` naming the model's page and what is lost."""
    with patch("huggingface_hub.model_info", side_effect=OSError("info fetch failed")):
        with caplog.at_level(
            logging.DEBUG, logger="pitloom.extract.remote.huggingface_fetch"
        ):
            result = _load_model_info("org/model")
    assert not result
    (record,) = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert getattr(record, CODE_ATTR) == DOWNLOAD_FAILED.code
    message = record.getMessage()
    assert "URL=https://huggingface.co/org/model: info fetch failed" in message
    assert message.endswith(MODEL_INFO_OUTCOME)


_HOSTILE = OSError("404 for o/m\n::error::forged\u202e")


@pytest.mark.parametrize(
    ("patched", "call"),
    [
        ("huggingface_hub.model_info", lambda: _load_model_info("o/m")),
        (
            "pathlib.Path.open",
            lambda: _detect_license_from_hf_files(
                _hub(Path("LICENSE")), "o/m", revision="1", license_files=["LICENSE"]
            ),
        ),
    ],
    ids=["model-info", "license-file"],
)
def test_a_hub_error_is_logged_on_one_escaped_line(
    patched: str, call: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A server-controlled error message cannot spill or forge a line."""
    with patch(patched, side_effect=_HOSTILE):
        call()
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    (message,) = [m for m in messages if "forged" in m]
    assert "\n" not in message and "\u202e" not in message


def test_the_licence_file_is_read_at_the_revision_model_info_listed_it_in(
    tmp_path: Path,
) -> None:
    """One ``model_info()`` request gives the revision and the licence file
    names, so a file is read at the commit whose listing named it."""
    licence = tmp_path / "LICENSE"
    licence.write_text("MIT License text", encoding="utf-8")
    info = _model_info(sha="a" * 40, siblings=[{"rfilename": "LICENSE"}])
    hub = _hub(licence)
    with (
        patch("huggingface_hub.model_info", return_value=info) as request,
        patch("pitloom.extract.remote.huggingface_fetch._load_model_card") as card,
        patch(
            "pitloom.extract._license_text_match.read_license_text",
            return_value=LicenseTextReading("MIT"),
        ),
    ):
        card.return_value = (None, {})
        data = _fetch_all_hf_data(hub, "org/model")
        found, _ = _resolve_license(hub, data, "org/model", {})
    assert found == "MIT"
    request.assert_called_once()
    licence_reads = [c for c in hub.read.call_args_list if c.args[1] == "LICENSE"]
    assert [c.kwargs["revision"] for c in licence_reads] == ["a" * 40]
