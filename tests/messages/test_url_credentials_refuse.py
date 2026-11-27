# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The helpers that say a URL credential written (the ``warn`` mode),
refused (the ``refuse`` mode) or accepted: each line has exactly one level
tag and its code, masks the secret, names the fingerprint where it takes
one, and stays one line when the URL holds a line break.

See also: :mod:`pitloom.messages.url_credentials`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import configure_logging
from pitloom.messages import (
    SURFACE_CLI,
    SURFACE_HOOK,
    SURFACE_LIBRARY,
    advice_surface,
    code_of,
    trusted_message,
)
from pitloom.messages.url_credentials import (
    refused_error,
    registry_file_refused_error,
    say_accepted,
    say_refused,
    say_stale_fingerprint,
    say_weak,
    say_written,
    warn_registry_file_entry_kept,
    warn_registry_key_kept,
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


#: Each surface's way of accepting a value, as its refusal ends.
_ADVICE_ENDS = {
    SURFACE_CLI: f"accept this value with --accept-url-credential {_FINGERPRINT}",
    SURFACE_HOOK: "accept this value by listing it in [tool.pitloom] "
    "accept-url-credentials",
    SURFACE_LIBRARY: "accept this value with "
    f'credentials=CredentialPolicy(accepted=["{_FINGERPRINT}"])',
}


@pytest.mark.parametrize("advice", sorted(_ADVICE_ENDS))
@pytest.mark.parametrize("url", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_say_refused_masks_and_names_the_way_its_surface_accepts(
    capsys: pytest.CaptureFixture[str], url: str, advice: str
) -> None:
    def say() -> None:
        with advice_surface(advice):
            say_refused(
                url,
                f"https://bob:{_SECRET}@h/el",
                "software_downloadLocation",
                _FINGERPRINT,
            )

    line = _one_line(_lines(capsys, say), "ERROR", "credentials-unsafe/refused")
    assert f"software_downloadLocation, {_FINGERPRINT}); " in line
    end = f"; remove it from the source, or {_ADVICE_ENDS[advice]}"
    assert line.endswith(f"{end} [credentials-unsafe/refused]")
    assert "allow" not in line


#: Each surface's way of turning the refuse mode on, as its warning ends.
_REFUSE_ENDS = {
    SURFACE_CLI: "refuse such values with --refuse-url-credentials",
    SURFACE_HOOK: 'refuse such values with [tool.pitloom] url-credentials = "refuse"',
    SURFACE_LIBRARY: "refuse such values with "
    "credentials=CredentialPolicy(refuse=True)",
}


@pytest.mark.parametrize("advice", sorted(_REFUSE_ENDS))
@pytest.mark.parametrize("url", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_say_written_every_time_names_the_way_its_surface_refuses(
    capsys: pytest.CaptureFixture[str], url: str, advice: str
) -> None:
    def twice() -> None:
        with advice_surface(advice):
            for _ in range(2):
                say_written(
                    url,
                    f"https://bob:{_SECRET}@h/el",
                    "software_downloadLocation",
                    _FINGERPRINT,
                )

    code = "credentials-unsafe/written"
    first, second = _lines(capsys, twice)
    assert first == second, "a second SBOM holding the value names it again"
    line = _one_line([first], "WARNING", code)
    assert f"software_downloadLocation, {_FINGERPRINT}); " in line
    end = (
        "; the SBOM states it as written; remove it from the source, or "
        f"{_REFUSE_ENDS[advice]}"
    )
    assert line.endswith(f"{end} [{code}]")


def test_say_written_names_each_value(capsys: pytest.CaptureFixture[str]) -> None:
    other = "sha256:fedcba9876543210"

    def two() -> None:
        say_written(_URL, "SPDXRef-a", "software_homePage", _FINGERPRINT)
        say_written(_URL + "y", "SPDXRef-a", "software_homePage", other)

    assert len(_lines(capsys, two)) == 2


def test_say_written_takes_only_a_fingerprint() -> None:
    with pytest.raises(ValueError, match="is not a fingerprint"):
        say_written(_URL, "SPDXRef-a", "software_homePage", "sha256:0123")


def test_the_library_advice_is_the_default_and_restored_on_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def say() -> None:
        with pytest.raises(KeyError), advice_surface(SURFACE_CLI):
            raise KeyError
        say_refused(_URL, "SPDXRef-a", "software_homePage", _FINGERPRINT)

    assert "CredentialPolicy(" in _lines(capsys, say)[0]


def test_advice_surface_takes_only_a_known_surface() -> None:
    with pytest.raises(InternalError), advice_surface("config"):
        pass


def test_say_refused_is_said_every_time(capsys: pytest.CaptureFixture[str]) -> None:
    """An error is never demoted to once per process: a second run names it."""

    def twice() -> None:
        for _ in range(2):
            say_refused(_URL, "SPDXRef-a", "software_homePage", _FINGERPRINT)

    assert len(_lines(capsys, twice)) == 2


def test_say_refused_takes_only_a_fingerprint() -> None:
    with pytest.raises(ValueError, match="is not a fingerprint"):
        say_refused(_URL, "SPDXRef-a", "software_homePage", "sha256:0123")


@pytest.mark.parametrize("advice", [SURFACE_CLI, SURFACE_LIBRARY])
@pytest.mark.parametrize("url", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_say_accepted_every_time(
    capsys: pytest.CaptureFixture[str], url: str, advice: str
) -> None:
    def twice() -> None:
        with advice_surface(advice):
            say_accepted(url, _FINGERPRINT)
            say_accepted(url, _FINGERPRINT)

    first, second = _lines(capsys, twice)
    assert first == second
    line = _one_line([first], "WARNING", "credentials-unsafe/accepted")
    assert line.endswith(
        f"that {_FINGERPRINT} accepts; the SBOM states it as written "
        "[credentials-unsafe/accepted]"
    )


@pytest.mark.parametrize(
    "url",
    [f"https://h/x?code={_SECRET}", f"https://h/x?code={_SECRET}\nERROR: forged"],
    ids=["plain", "line-break"],
)
def test_say_weak_every_time(capsys: pytest.CaptureFixture[str], url: str) -> None:
    def twice() -> None:
        say_weak(url)
        say_weak(url)

    first, second = _lines(capsys, twice)
    assert first == second
    line = _one_line([first], "WARNING", "credentials-unsafe")
    assert "the SBOM states it as written" in line


def test_say_stale_fingerprint(capsys: pytest.CaptureFixture[str]) -> None:
    def twice() -> None:
        say_stale_fingerprint(_FINGERPRINT, "urn:doc-a")
        say_stale_fingerprint(_FINGERPRINT, "urn:doc-a")

    line = _one_line(_lines(capsys, twice), "WARNING", "option-no-effect")
    assert line == (
        f"WARNING: Options: FINGERPRINT={_FINGERPRINT}: matches no URL of the "
        "SBOM urn:doc-a [option-no-effect]"
    )


def test_say_stale_fingerprint_once_per_sbom(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A batch (``embed-wheel`` of several wheels) names each SBOM."""

    def batch() -> None:
        for document in ("urn:doc-b", "urn:doc-c", "urn:doc-b"):
            say_stale_fingerprint(_FINGERPRINT, document)

    lines = _lines(capsys, batch)
    assert [line.split(" SBOM ")[1] for line in lines] == [
        "urn:doc-b [option-no-effect]",
        "urn:doc-c [option-no-effect]",
    ]


@pytest.mark.parametrize(
    ("count", "wanted"), [(1, "1 URL value(s)"), (12, "12 URL value(s)")]
)
def test_refused_error_names_no_url(count: int, wanted: str) -> None:
    exc = refused_error(count)
    assert code_of(exc) == "credentials-unsafe/refused"
    assert str(exc) == f"{wanted} in the SBOM hold credentials; the SBOM is refused"
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
    assert f"ID registry file '{file}' is not loaded; remove the entry" in text
    assert sum(text.count(tag) for tag in _LEVELS) == (key == _BROKEN)
    assert trusted_message(f"ERROR: {text} [credentials-unsafe/registry]") is not None


def test_the_helpers_log_under_pitloom(caplog: pytest.LogCaptureFixture) -> None:
    """The records reach a handler on ``pitloom`` (the library's, the hook's)."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        say_weak("https://h/?session=1")
    (record,) = caplog.records
    assert record.name.startswith("pitloom.")


@pytest.mark.parametrize("key", [_URL, _BROKEN], ids=["plain", "line-break"])
def test_registry_warnings_in_the_warn_mode_once_per_value(
    capsys: pytest.CaptureFixture[str], key: str
) -> None:
    log = logging.getLogger("pitloom.id_registry")

    def twice() -> None:
        for _ in range(2):
            warn_registry_key_kept(log, key)
            warn_registry_file_entry_kept(log, "ids.json", key)

    code = "credentials-unsafe/registry"
    kept, loaded = _lines(capsys, twice)
    assert _one_line([kept], "WARNING", code).endswith(
        f"; the ID registry stores the key as written [{code}]"
    )
    assert _one_line([loaded], "WARNING", code).endswith(
        f"; ID registry file 'ids.json' is loaded as it is; remove the entry [{code}]"
    )
