# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel and embedded-SBOM writers under attacker text (catalogue PR
16, step 1): a member name, an archive name, a ``--sbom-filename``, a
``METADATA`` or SBOM value and ``spdx3-validate``'s text may hold a line
break with a forged ``WARNING:`` and code, an escape sequence, a URL
credential, 64 KiB, both quotes or a NUL. Each writer masks, cuts, quotes
and escapes it itself: one line that keeps its own code; a name is cut to
NAME_CHARACTERS, a declared value to its excerpt.

See also: tests/messages/test_wheels_core.py,
tests/messages/test_wheels_core_sboms.py and
tests/messages/test_wheels_core_worst_case.py (every line at its longest).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.logging_config import CODE_ATTR, EXCERPT_CHARS
from pitloom.messages import MESSAGES, code_of, trusted_message
from pitloom.messages import wheel_sboms as s
from pitloom.messages import wheels as w
from pitloom.messages._field_writers import NAME_CHARACTERS, NAME_CUT_MARK
from pitloom.messages._fields_wheels import identity_part_text, quoted_names_text
from pitloom.messages.targets import relay_validator_text

pytestmark = pytest.mark.platform  # escapes, NUL and line ends in names

#: A Pitloom logger, so the record check of tests/conftest.py also
#: trusts each line: a 64 KiB name is cut, never past LONGEST_LINE.
_LOG = logging.getLogger("pitloom.core.wheel_dist_info")
_BIG = "x" * 65536
#: A line break with a forged line and code, an escape, a URL credential,
#: 64 KiB, both quotes, a NUL.
_HOSTILE = {
    "forged": "a\nWARNING: x [wheel-invalid]\r",
    "escape": "\x1b[31mred\u2028",
    "credential": "https://u:pw@h/m.py",
    "long": _BIG,
    "quotes": 'it\'s "q"',
    "nul": "a\x00b.py",
}


def _check(text: str, code: str, level: str, *, cut: bool = False) -> None:
    """*text* (a line's text, no tag) is one masked, escaped line that keeps
    *code*; with *cut*, the 64 KiB name in it is cut to NAME_CHARACTERS."""
    assert "\n" not in text and "\r" not in text and "\x00" not in text
    assert "\x1b" not in text and "\u2028" not in text
    assert ":pw@" not in text
    if cut:
        assert "x" * NAME_CHARACTERS + NAME_CUT_MARK in text
        assert "x" * (NAME_CHARACTERS + 1) not in text
    assert trusted_message(f"{level}: {text} [{code}]") is MESSAGES[code]
    assert trusted_message(f"{level}: {text} [over-cap]") is None


_REFUSALS: dict[str, Callable[[str], w.WheelRefused]] = {
    "nul": lambda name: w.refuse_nul_name("demo.whl", name),
    "duplicate": lambda name: w.refuse_duplicate_name(name, "m"),
    "member": lambda name: w.refuse_unreadable_member("demo.whl", name, EOFError()),
    "conforming": lambda name: w.refuse_non_conforming("demo.whl", name),
    "signed": lambda name: w.refuse_signed("demo.whl", name),
    "archive": lambda name: w.refuse_dist_info(name, w.DIST_INFO_NONE),
}


@pytest.mark.parametrize("value", _HOSTILE.values(), ids=list(_HOSTILE))
@pytest.mark.parametrize("make", _REFUSALS.values(), ids=list(_REFUSALS))
def test_a_refusal_names_a_hostile_name_safely(
    make: Callable[[str], w.WheelRefused], value: str
) -> None:
    exc = make(value)
    code = code_of(exc)
    assert code is not None
    _check(str(exc), code, "ERROR", cut=value is _BIG)


def _record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    (record,) = caplog.records
    caplog.clear()
    return record


@pytest.mark.parametrize("value", _HOSTILE.values(), ids=list(_HOSTILE))
def test_a_member_line_names_hostile_names_safely(
    caplog: pytest.LogCaptureFixture, value: str
) -> None:
    cut = value is _BIG
    sayers: list[Callable[[], None]] = [
        lambda: w.warn_archive_member(_LOG, w.MEMBER_UNSAFE, value, value),
        lambda: w.warn_archive_member(
            _LOG, w.MEMBER_OVERWRITTEN, "a.whl", "m", later=value
        ),
        lambda: w.warn_archive_member(
            _LOG, w.MEMBER_NORMALISED, "a.whl", "m", listed_as=value
        ),
        lambda: w.warn_shared_paths(_LOG, "a.tar.gz", [value, value]),
        lambda: w.warn_dist_info(_LOG, "a.whl", w.DIST_INFO_OTHER, chosen=value),
        lambda: w.warn_metadata_missing(_LOG, "a.whl", value),
        lambda: s.warn_wrong_extension(_LOG, "a.whl", value, ".spdx3.json"),
        lambda: s.say_held_sbom(_LOG, value, value, removed=False),
    ]
    for say in sayers:
        say()
        record = _record(caplog)
        _check(record.getMessage(), getattr(record, CODE_ATTR), "WARNING", cut=cut)


@pytest.mark.parametrize("value", _HOSTILE.values(), ids=list(_HOSTILE))
def test_an_sbom_error_names_hostile_names_safely(value: str) -> None:
    cut = value is _BIG
    for exc in (
        s.wheel_sbom_ambiguous("a.whl", [value, "b"]),
        s.wheel_sbom_missing(value, value),
        s.sbom_name_conflict("a.json", value),
    ):
        code = code_of(exc)
        assert code is not None
        _check(str(exc), code, "ERROR", cut=cut)


@pytest.mark.parametrize(
    "value",
    [*_HOSTILE.values(), "N" * 10_000_000],
    ids=[*_HOSTILE, "ten-megabytes"],
)
def test_a_declared_value_is_cut_to_its_excerpt(
    caplog: pytest.LogCaptureFixture, value: str
) -> None:
    mismatch = s.IdentityMismatch("name", value, value)
    s.say_identity_mismatches(_LOG, "a.whl", [mismatch])
    s.warn_cross_check_gaps(
        _LOG, "a.whl", [s.CrossCheckGap(s.GAP_SBOM_VERSION_INVALID, value=value)]
    )
    exc = s.identity_mismatch_error(_LOG, "a.whl", [mismatch])
    texts = [r.getMessage() for r in caplog.records]
    for text in [*texts, str(exc)]:
        code = "wheel-sbom-conflict" if "differs" in text else "wheel-sbom-unusable"
        _check(text, code, "WARNING")
    # Each value is at most an excerpt.
    assert all(len(t) < 2 * EXCERPT_CHARS + 120 for t in [*texts, str(exc)])


@pytest.mark.parametrize("value", _HOSTILE.values(), ids=list(_HOSTILE))
def test_the_validator_relay_keeps_each_line_one_line(
    capsys: pytest.CaptureFixture[str], value: str
) -> None:
    relay_validator_text(f"finding {value}")
    for line in capsys.readouterr().err.splitlines():
        assert line.startswith("ERROR: spdx3-validate: ")
        assert "\x1b" not in line and ":pw@" not in line and "\x00" not in line
        assert trusted_message(line) is None


@pytest.mark.parametrize("as_path", [False, True], ids=["str", "path"])
def test_an_archive_is_named_by_its_file_name_only(as_path: bool) -> None:
    given = os.path.join(tempfile.gettempdir(), "secret-dir", "demo.whl")
    exc = w.refuse_dist_info(Path(given) if as_path else given, w.DIST_INFO_NONE)
    assert str(exc).startswith("ARCHIVE='demo.whl': ")
    assert "secret-dir" not in str(exc)


def test_an_in_memory_zip_has_no_archive_name() -> None:
    with pytest.raises(ValueError, match="not an archive name") as caught:
        w.refuse_dist_info(None, w.DIST_INFO_NONE)  # type: ignore[arg-type]
    assert code_of(caught.value) is None


@pytest.mark.parametrize(
    "value", ["name", b"x", None, 3], ids=["str", "bytes", "none", "int"]
)
def test_a_names_list_that_is_no_list_is_refused(value: object) -> None:
    """A ``str`` is not a list of one name: it would be read letter by letter."""
    with pytest.raises(ValueError, match="not a list"):
        quoted_names_text(value)


@pytest.mark.parametrize(
    "value", ["", "Name", "build", None], ids=["empty", "case", "other", "none"]
)
def test_an_identity_part_is_name_or_version_only(value: object) -> None:
    with pytest.raises(ValueError, match="not a part"):
        identity_part_text(value)
    assert identity_part_text("name") == "name"
    assert identity_part_text("version") == "version"


#: (wheel, SBOM) values that differ only in white space or past the cut.
_LOOK_ALIKES = {
    "tab": ("demo", "demo\t"),
    "double-space": ("my pkg", "my  pkg"),
    "nbsp": ("demo", "demo\u00a0"),
    "trailing-space": ("demo", "demo "),
    "white-space-only": ("demo", "   "),
    "longer-past-cut": ("a" * (EXCERPT_CHARS + 1), "a" * (EXCERPT_CHARS + 10)),
    "equal-length-past-cut": ("a" * 130 + "b", "a" * 130 + "c"),
}
_SIDES = re.compile(r"SBOM name (.+) differs from the wheel's METADATA (.+)")


@pytest.mark.parametrize(
    ("wheel", "sbom"), _LOOK_ALIKES.values(), ids=list(_LOOK_ALIKES)
)
def test_a_mismatch_line_tells_the_two_sides_apart(
    caplog: pytest.LogCaptureFixture, wheel: str, sbom: str
) -> None:
    assert wheel != sbom
    mismatch = s.IdentityMismatch("name", wheel, sbom)
    s.say_identity_mismatches(_LOG, "a.whl", [mismatch])
    exc = s.identity_mismatch_error(_LOG, "a.whl", [mismatch])
    record = _record(caplog)
    for text, level in ((record.getMessage(), "WARNING"), (str(exc), "ERROR")):
        _check(text, "wheel-sbom-conflict", level)
        found = _SIDES.search(text)
        assert found is not None, text
        shown_sbom, shown_wheel = found.groups()
        assert shown_sbom != shown_wheel
        assert shown_sbom.startswith("'") and shown_wheel.startswith("'")
