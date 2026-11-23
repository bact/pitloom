# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom fragment list`` reads the project's metadata for its own document
id (:func:`pitloom.assemble.project_document_id`) and goes on when that
fails: every coded error it can meet there is said again as a ``WARNING``
through :func:`pitloom.messages.metadata.relay_coded_warning`, so each needs
a ``WARNING`` twin (PR 15, Q9). The corpus is PR 12's metadata errors plus a
broken ID registry; two errors it cannot meet keep no twin.

See also: tests/messages/test_metadata_relays.py (the relays of the project
readers themselves).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.assemble import project_document_id
from pitloom.cli.commands import fragment as fragment_cmd
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import MESSAGES, code_of, trusted_message
from pitloom.messages.metadata import relay_coded_warning

pytestmark = pytest.mark.platform

_BIG_VERSION = '[project]\nname = "demo"\nversion = "1.' + "9" * 700 + '"\n'
_REGISTRY = (
    '[project]\nname = "demo"\nversion = "1"\n[tool.pitloom]\n'
    'id-registry = "reg.json"\n'
)


def _project(root: Path, files: dict[str, str | bytes]) -> Path:
    """A project directory holding a package ``demo`` and *files*."""
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    for name, content in files.items():
        data = content.encode() if isinstance(content, str) else content
        (root / name).write_bytes(data)
    return root


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ({"pyproject.toml": _BIG_VERSION}, "metadata-invalid"),
        (
            {"pyproject.toml": '[project]\nname = "-bad-"\nversion = "1"\n'},
            "metadata-invalid",
        ),
        ({"pyproject.toml": "[project]\nname = 5\n"}, "metadata-invalid"),
        ({"pyproject.toml": "project = 'x'\n"}, "metadata-invalid"),
        ({"setup.cfg": "[metadata]\nversion = 1\n"}, "project-name-missing"),
        ({"pyproject.toml": "a = 1\r\nc = = 3\r\n"}, "config-malformed"),
        ({"pyproject.toml": b"\xff\xfe[project]\n"}, "file-unreadable/not-utf8"),
        ({"setup.cfg": "[metadata\nname = demo\n"}, "config-malformed"),
        (
            {"setup.cfg": "[metadata]\nname = demo\nversion = 100%\n"},
            "config-malformed",
        ),
        ({"pyproject.toml": _REGISTRY, "reg.json": "{not json"}, "json-malformed"),
    ],
    ids=[
        "number",
        "name-invalid",
        "name-integer",
        "project-string",
        "no-name",
        "toml",
        "not-utf8",
        "ini",
        "interpolation",
        "registry",
    ],
)
def test_every_error_fragment_list_can_meet_is_relayed_with_its_code(
    files: dict[str, str | bytes],
    code: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = _project(tmp_path / "p", files)
    with pytest.raises(Exception) as raised:  # noqa: B017 - any coded error
        project_document_id(root)
    assert code_of(raised.value) == code
    configure_logging()
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        relay_coded_warning(logging.getLogger("pitloom.cli"), raised.value, quiet=False)
    (record,) = caplog.records
    line = f"WARNING: {record.getMessage()} [{getattr(record, CODE_ATTR)}]"
    assert trusted_message(line) is MESSAGES[code]


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"pyproject.toml": '[project]\nname = "demo"\n[tool.pitloom]\nfragment = 3\n'},
    ],
    ids=["project-not-found", "config-invalid"],
)
def test_errors_fragment_list_cannot_meet_keep_no_twin(
    files: dict[str, str | bytes], tmp_path: Path
) -> None:
    """``fragment list`` reads ``[tool.pitloom]`` from ``pyproject.toml``
    before it asks for the document id, and stops (or lists nothing) when
    that file or table is missing or wrong: these two never reach the relay,
    so they stay ERROR-only and a relay of one is a programming error."""
    root = _project(tmp_path / "p", files)
    with pytest.raises(Exception) as raised:  # noqa: B017 - any coded error
        project_document_id(root)
    assert code_of(raised.value) in {"project-not-found", "config-invalid"}
    with pytest.raises(InternalError, match="no WARNING line relays it"):
        relay_coded_warning(logging.getLogger("pitloom.cli"), raised.value, quiet=True)


@pytest.mark.parametrize("error", [InternalError("x"), MemoryError()], ids=["i", "m"])
def test_own_document_id_does_not_swallow_a_defect(
    error: BaseException, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A programming error or an out-of-memory in the metadata read ends the
    listing; only an ordinary read failure leaves ``SAME_DOCUMENT=-``."""

    def _boom(_project_dir: Path) -> str:
        raise error

    monkeypatch.setattr(fragment_cmd, "project_document_id", _boom)
    with pytest.raises(type(error)) as raised:
        fragment_cmd._own_document_id(tmp_path)  # pylint: disable=protected-access
    assert raised.value is error  # re-raised as it was, not relayed
