# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The helpers that say a refused or accepted URL credential: each line
has exactly one level tag and its code, masks the secret, names the
fingerprint where it takes one, and stays one line when the URL holds a
line break.

See also: :mod:`pitloom.messages.url_credentials`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import configure_logging
from pitloom.messages import code_of, trusted_message
from pitloom.messages.url_credentials import (
    refused_error,
    registry_file_refused_error,
    say_accepted,
    say_config_cli_only,
    say_refused,
    say_stale_fingerprint,
    say_weak,
)

#: A registry file is named by a path, spelt per platform.
pytestmark = pytest.mark.platform

_SECRET = "s3cr3tPw"
_URL = f"https://alice:{_SECRET}@example.org/x"
#: A line break and a forged second tagged line in the URL.
_BROKEN = f"https://alice:{_SECRET}@example.org/x\nERROR: forged"
_FINGERPRINT = "sha256:0123456789abcdef"
_LEVELS = ("ERROR: ", "WARNING: ", "INFO: ")


def _lines(capsys: pytest.CaptureFixture[str], say: Callable[[], None]) -> list[str]:
    configure_logging()
    say()
    return capsys.readouterr().err.splitlines()


def _one_line(lines: list[str], level: str, code: str) -> str:
    """The only line printed: one level tag at its start (a forged one stays
    inside the escaped value), and *code* last."""
    (line,) = lines
    assert line.startswith(f"{level}: ")
    forged = "\\nERROR: forged" in line
    assert sum(line.count(tag) for tag in _LEVELS) == 1 + forged
    assert line.endswith(f" [{code}]")
    assert trusted_message(line) is not None
    assert _SECRET not in line
    return line


@pytest.mark.parametrize("url", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_say_refused_masks_and_names_the_fingerprint_twice(
    capsys: pytest.CaptureFixture[str], url: str
) -> None:
    lines = _lines(
        capsys,
        lambda: say_refused(
            url,
            f"https://bob:{_SECRET}@h/el",
            "software_downloadLocation",
            _FINGERPRINT,
        ),
    )
    line = _one_line(lines, "ERROR", "credentials-unsafe/refused")
    assert line.count(_FINGERPRINT) == 2
    assert "software_downloadLocation" in line
    assert "--accept-url-credential " in line
    assert "--allow-url-credentials" not in line


def test_say_refused_is_said_every_time(capsys: pytest.CaptureFixture[str]) -> None:
    """An error is never demoted to once per process: a second run names it."""

    def twice() -> None:
        for _ in range(2):
            say_refused(_URL, "SPDXRef-a", "software_homePage", _FINGERPRINT)

    assert len(_lines(capsys, twice)) == 2


def test_say_refused_takes_only_a_fingerprint() -> None:
    with pytest.raises(ValueError, match="is not a fingerprint"):
        say_refused(_URL, "SPDXRef-a", "software_homePage", "sha256:0123")


@pytest.mark.parametrize(
    ("fingerprint", "wanted"),
    [(_FINGERPRINT, f"that {_FINGERPRINT} accepts"), (None, "--allow-url-credentials")],
    ids=["fingerprint", "global"],
)
@pytest.mark.parametrize("url", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_say_accepted_once_per_value(
    capsys: pytest.CaptureFixture[str], url: str, fingerprint: str | None, wanted: str
) -> None:
    def twice() -> None:
        say_accepted(url, fingerprint)
        say_accepted(url, fingerprint)

    line = _one_line(_lines(capsys, twice), "WARNING", "credentials-unsafe/accepted")
    assert wanted in line
    assert "the SBOM states it as written" in line or "keeps it as written" in line


@pytest.mark.parametrize(
    "url",
    [f"https://h/x?code={_SECRET}", f"https://h/x?code={_SECRET}\nERROR: forged"],
    ids=["plain", "line-break"],
)
def test_say_weak_once_per_value(capsys: pytest.CaptureFixture[str], url: str) -> None:
    def twice() -> None:
        say_weak(url)
        say_weak(url)

    line = _one_line(_lines(capsys, twice), "WARNING", "credentials-unsafe")
    assert "the SBOM states it as written" in line


def test_say_stale_fingerprint(capsys: pytest.CaptureFixture[str]) -> None:
    def twice() -> None:
        say_stale_fingerprint(_FINGERPRINT)
        say_stale_fingerprint(_FINGERPRINT)

    line = _one_line(_lines(capsys, twice), "WARNING", "option-no-effect")
    assert line == (
        f"WARNING: Options: FINGERPRINT={_FINGERPRINT}: matches no URL of this "
        "SBOM [option-no-effect]"
    )


@pytest.mark.parametrize("table", ["[tool.pitloom]", "[tool:pitloom]"])
def test_say_config_cli_only(capsys: pytest.CaptureFixture[str], table: str) -> None:
    def twice() -> None:
        say_config_cli_only("allow-url-credentials", table=table)
        say_config_cli_only("allow-url-credentials", table=table)

    line = _one_line(_lines(capsys, twice), "WARNING", "config-unsafe/cli-only")
    assert line == (
        f"WARNING: allow-url-credentials: CLI only; ignored in {table} "
        "[config-unsafe/cli-only]"
    )


@pytest.mark.parametrize(
    ("count", "wanted"), [(1, "1 URL value(s)"), (12, "12 URL value(s)")]
)
def test_refused_error_names_no_url(count: int, wanted: str) -> None:
    exc = refused_error(count)
    assert code_of(exc) == "credentials-unsafe/refused"
    assert str(exc) == f"{wanted} in the SBOM hold credentials; no SBOM is written"
    assert trusted_message(f"ERROR: {exc} [credentials-unsafe/refused]") is not None


@pytest.mark.parametrize("count", [0, -1, True], ids=["zero", "negative", "bool"])
def test_refused_error_needs_a_count(count: int) -> None:
    with pytest.raises(InternalError):
        refused_error(count)


@pytest.mark.parametrize("key", [_URL, _BROKEN], ids=["plain", "line-break"])
@pytest.mark.parametrize("file", ["ids.json", Path("reg") / "ids.json"])
def test_registry_file_refused_error(key: str, file: str | Path) -> None:
    exc = registry_file_refused_error(file, key)
    text = str(exc)
    assert code_of(exc) == "credentials-unsafe/registry"
    assert _SECRET not in text and "\n" not in text
    assert f"ID registry file {file} is not loaded; remove the entry" in text
    assert sum(text.count(tag) for tag in _LEVELS) == (key == _BROKEN)
    assert trusted_message(f"ERROR: {text} [credentials-unsafe/registry]") is not None


def test_the_helpers_log_under_pitloom(caplog: pytest.LogCaptureFixture) -> None:
    """The records reach a handler on ``pitloom`` (the library's, the hook's)."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        say_weak("https://h/?session=1")
    (record,) = caplog.records
    assert record.name.startswith("pitloom.")
