# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The configuration families' mechanism: where a value sits
(:class:`ConfigPlace`, the one place spelling ``.`` or ``:``), what was
found (``got``: TOML type names, a ``bool`` before an ``int``, a string
masked, escaped and cut), the closed ``expected`` table, and
:meth:`ConfigError.located`, the one place a file is added.

See also: tests/messages/test_config_drift.py (the tables against the
readers, import order).
"""

from __future__ import annotations

import copy
import datetime
import logging
import pickle  # nosec B403
from collections.abc import Callable
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    CodedFileNotFoundError,
    CodedValueError,
    code_of,
    recoded,
    trusted_message,
)
from pitloom.messages.config import (
    CONFIG_INVALID,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
    MISSING,
    SHOWN_CHARS,
    ConfigError,
    ConfigPlace,
    Parameter,
    config_invalid,
    config_moved,
    found_text,
    hook_unknown_keys,
    invalid_value,
    kind_text,
    must_be,
    warn_config_unknown_key,
)
from pitloom.messages.options import OPTION_INVALID
from pitloom.messages.targets import input_not_found
from tests._message_drift import raised_as

_LOG = logging.getLogger("pitloom.config_messages")
_TOP = ConfigPlace("tool.pitloom")


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


@pytest.mark.parametrize(
    ("place", "toml", "ini"),
    [
        (_TOP.at("pretty"), "[tool.pitloom] pretty", "[tool:pitloom] pretty"),
        (
            ConfigPlace("tool.pitloom.provenance"),
            "[tool.pitloom.provenance]",
            "[tool:pitloom:provenance]",
        ),
        (
            ConfigPlace("tool.pitloom.creator", entry=0, sub="type"),
            "[[tool.pitloom.creator]] entry 0 type",
            "[tool:pitloom:creator] entry 0 type",
        ),
        (
            ConfigPlace("tool.pitloom.fragment", "files").entry_at(2).at("role"),
            "[tool.pitloom.fragment] files entry 2 role",
            "[tool:pitloom:fragment] files entry 2 role",
        ),
        (
            ConfigPlace("tool.pitloom.content-type.override").entry_at(0),
            "[[tool.pitloom.content-type.override]] entry 0",
            "[tool:pitloom:content-type:override] entry 0",
        ),
        (ConfigPlace("tool"), "[tool]", "[tool]"),
    ],
    ids=["key", "table", "array-entry", "inline-entry", "nested-array", "tool"],
)
def test_a_place_is_spelt_for_its_source(
    place: ConfigPlace, toml: str, ini: str
) -> None:
    assert (place.text, place.spelt(True).text) == (toml, ini)
    assert place.spelt(True).spelt(False) == place


@pytest.mark.parametrize(
    "build",
    [
        lambda: ConfigPlace("tool.pitloom.nope"),
        lambda: ConfigPlace("tool.pitloom", "Pretty"),
        lambda: ConfigPlace("tool.pitloom", "a b"),
        lambda: ConfigPlace("tool.pitloom", "files", sub="role"),
        lambda: ConfigPlace("tool.pitloom.creator", "name"),
        lambda: ConfigPlace("tool.pitloom", entry=0),
        lambda: ConfigPlace("tool.pitloom", "files", entry=-1),
        lambda: ConfigPlace("tool.pitloom", "files", entry=True),
        lambda: _TOP.at("pretty").at("again"),
        lambda: ConfigPlace("tool.pitloom.creator").at("name"),
        lambda: _TOP.entry_at(0),
        lambda: ConfigPlace("tool.pitloom.creator", entry=0).entry_at(1),
        lambda: Parameter("max bytes"),
    ],
    ids=[
        "table",
        "upper",
        "space",
        "sub-no-entry",
        "array-key",
        "table-entry",
        "negative",
        "bool-entry",
        "key-twice",
        "array-key-at",
        "no-array",
        "entry-twice",
        "parameter",
    ],
)
def test_a_place_that_does_not_nest_is_a_programming_error(
    build: Callable[[], object],
) -> None:
    with pytest.raises(InternalError):
        build()


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (MISSING, "nothing"),
        (None, "None"),
        (True, "a boolean true"),
        (False, "a boolean false"),
        (0, "an integer 0"),
        (-1, "an integer -1"),
        (10**39 - 1, f"an integer {10**39 - 1}"),
        (-(10**39), "an integer of 40 digits or more"),
        (1.5, "a float 1.5"),
        (float("inf"), "a float inf"),
        ("", "a string ''"),
        ("maybe", "a string 'maybe'"),
        ("x" * SHOWN_CHARS, f"a string '{'x' * SHOWN_CHARS}'"),
        ("x" * (SHOWN_CHARS + 1), f"a string '{'x' * SHOWN_CHARS}'..."),
        ("it's", 'a string "it\'s"'),
        (datetime.datetime(2026, 1, 1), "a date-time"),
        (datetime.date(2026, 1, 1), "a date"),
        (datetime.time(1, 2), "a time"),
        ([1, "secret"], "an array"),
        ((1,), "an array"),
        ({"token": "secret"}, "a table"),
        (object(), "a value of type object"),
    ],
    ids=[
        "missing",
        "none",
        "true",
        "false",
        "zero",
        "negative",
        "39-digits",
        "40-digits",
        "float",
        "inf",
        "empty",
        "string",
        "at-cut",
        "past-cut",
        "quote",
        "datetime",
        "date",
        "time",
        "list",
        "tuple",
        "dict",
        "object",
    ],
)
def test_what_was_found_is_named_by_its_toml_type(value: object, text: str) -> None:
    assert found_text(value) == text


def test_a_numpy_integer_is_an_integer_and_a_numpy_float_a_float() -> None:
    numpy = pytest.importorskip("numpy")
    assert found_text(numpy.int64(-3)) == "an integer -3"
    assert found_text(numpy.float64(1.5)) == "a float 1.5"
    assert found_text(numpy.bool_(True)) == "a value of type bool"


def test_a_type_of_an_odd_name_is_not_named() -> None:
    odd = type("\u00e9t\u00e9", (), {})
    assert found_text(odd()) == "a value of another type"


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("a\nb", r"'a\nb'"),
        ("\x1b[31mred", r"'\x1b[31mred'"),
        ("\udc80x", r"'\udc80x'"),
        ("https://u:pass@h/x", "'https://***:***@h/x'"),
        ("https://user:" + "p" * 60 + "@h/", "'https://***:***@h/'"),
    ],
    ids=["newline", "escape", "surrogate", "url", "url-past-cut"],
)
def test_a_string_found_is_masked_escaped_and_on_one_line(
    value: str, shown: str
) -> None:
    exc = config_invalid(_TOP.at("pretty"), "boolean", got=value).located(
        "pyproject.toml", False
    )
    text = str(exc)
    assert text.endswith(f"got a string {shown}") and "\n" not in text
    assert "pass" not in text and "pass" not in repr(exc.args)
    assert raised_as(exc, CONFIG_INVALID)


def test_a_secret_is_named_by_its_type_only() -> None:
    exc = config_invalid(
        _TOP.at("accept-url-credentials"), "fingerprints", "ghp_token", secret=True
    )
    assert str(exc).endswith("must be an array of fingerprints, got a string")
    assert "ghp_token" not in repr(vars(exc)) + repr(exc.args)
    assert kind_text(5) == "an integer" and kind_text(MISSING) == "nothing"


def test_a_bool_is_never_an_integer() -> None:
    """``isinstance(True, int)``: a ``bool`` is checked first."""
    exc = config_invalid(_TOP.at("max-download-bytes"), "positive", got=True)
    assert str(exc).endswith("got a boolean true")


def test_located_adds_the_file_once_and_spells_the_source() -> None:
    raw = config_invalid(_TOP.at("pretty"), "boolean", got="maybe")
    assert str(raw) == (
        "[tool.pitloom] pretty: must be true or false, got a string 'maybe'"
    )
    toml = raw.located("p/pyproject.toml", False)
    assert str(toml) == (
        "FILE=p/pyproject.toml: [tool.pitloom] pretty: must be true or false, "
        "got a string 'maybe'"
    )
    ini = raw.located("setup.cfg", True)
    assert str(ini).startswith("FILE=setup.cfg: [tool:pitloom] pretty: ")
    assert toml.located("other.toml", True) is toml
    assert str(raw.located(None, True)).startswith("[tool:pitloom] pretty: ")
    for exc in (raw, toml, ini):
        assert isinstance(exc, ConfigError) and isinstance(exc, ValueError)
        assert raised_as(exc, CONFIG_INVALID)


def test_located_reads_back_with_a_windows_path() -> None:
    path = PureWindowsPath(r"C:\p\pyproject.toml")
    exc = config_moved(_TOP.at("ids-file"), "[tool.pitloom] id-registry")
    text = str(exc.located(path, False))
    assert text == (
        r"FILE=C:\p\pyproject.toml: [tool.pitloom] ids-file: moved to "
        "[tool.pitloom] id-registry"
    )
    assert trusted_message(f"ERROR: {text} [config-moved]") is CONFIG_MOVED


def test_located_is_raised_from_none_and_names_nothing_secret() -> None:
    def parse() -> None:
        try:
            raise config_invalid(_TOP.at("pretty"), "boolean", "https://u:pw@h/")
        except ConfigError as exc:
            raise exc.located("pyproject.toml", False) from None

    with pytest.raises(ConfigError) as caught:
        parse()
    assert caught.value.__suppress_context__ and caught.value.__cause__ is None
    assert "pw" not in str(caught.value) + repr(vars(caught.value))


@pytest.mark.parametrize("again", [copy.copy, lambda e: pickle.loads(pickle.dumps(e))])
def test_a_copy_keeps_its_text_and_code_and_is_not_located_again(
    again: Callable[[ConfigError], ConfigError],
) -> None:
    exc = config_invalid(_TOP.at("pretty"), "boolean", "x").located("a.toml", False)
    copied = again(exc)
    assert isinstance(copied, ConfigError)
    assert (str(copied), code_of(copied), copied.args) == (
        str(exc),
        "config-invalid",
        (str(exc),),
    )
    unlocated = again(config_invalid(_TOP.at("pretty"), "boolean"))
    assert unlocated.located("b.toml", True) is unlocated


@pytest.mark.parametrize(
    "build",
    [
        lambda: config_invalid(_TOP.at("pretty"), "bool"),
        lambda: config_invalid(
            "[tool.pitloom] pretty",  # type: ignore[arg-type]
            "boolean",
        ),
        lambda: must_be("bool"),
        lambda: invalid_value(Parameter("x"), "bool"),
        lambda: invalid_value("max_bytes", "positive"),  # type: ignore[arg-type]
    ],
    ids=["id", "table-string", "must-be", "parameter-id", "stage"],
)
def test_an_unknown_id_or_stage_is_a_programming_error(
    build: Callable[[], object],
) -> None:
    with pytest.raises(InternalError):
        build()


def test_a_moved_key_names_only_a_known_destination() -> None:
    with pytest.raises(ValueError, match="destination"):
        config_moved(_TOP.at("ids-file"), "somewhere else")


def test_the_stage_picks_the_code() -> None:
    """One validator, two stages: a setting is the user's (``config-invalid``),
    a library value the caller's (``option-invalid``)."""
    config = invalid_value(_TOP.at("max-download-bytes"), "positive", 0)
    library = invalid_value(Parameter("max_download_bytes"), "positive", 0)
    assert isinstance(config, ConfigError) and raised_as(config, CONFIG_INVALID)
    assert not isinstance(library, ConfigError) and raised_as(library, OPTION_INVALID)
    assert str(library) == (
        "max_download_bytes: must be an integer of at least 1, got an integer 0"
    )
    assert must_be("budget", 3) == (
        "must be 0 (no cap) or an integer of at least 8, got an integer 3"
    )


@pytest.mark.parametrize(
    ("hint", "tail"),
    [
        ({"setting": "pretty"}, "unknown key prety; did you mean pretty?"),
        (
            {"tables": (ConfigPlace("tool.pitloom.provenance"),)},
            "unknown key prety; it belongs in [tool.pitloom.provenance]",
        ),
        ({}, "unknown key prety"),
    ],
    ids=["close", "elsewhere", "none"],
)
@pytest.mark.parametrize("file", ["p/pyproject.toml", None], ids=["file", "no-file"])
def test_an_unknown_key_is_said_once_with_its_hint(
    caplog: pytest.LogCaptureFixture,
    hint: dict[str, object],
    tail: str,
    file: str | None,
) -> None:
    caplog.set_level(logging.DEBUG)
    for _ in range(2):
        warn_config_unknown_key(
            _LOG,
            _TOP,
            "prety",
            file=file,
            once=f"{file} {tail}",
            **hint,  # type: ignore[arg-type]
        )
    (line,) = [p for p in _printed(caplog) if p.startswith("WARNING")]
    head = f"FILE={file}: " if file else ""
    assert line == f"WARNING: {head}[tool.pitloom]: {tail} [config-unknown-key]"
    assert trusted_message(line) is CONFIG_UNKNOWN_KEY
    assert [r.levelname for r in caplog.records] == ["WARNING", "DEBUG"]


def test_an_unknown_key_is_escaped(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    warn_config_unknown_key(_LOG, _TOP.spelt(True), "a\nb", file="setup.cfg")
    (line,) = _printed(caplog)
    assert line == (
        "WARNING: FILE=setup.cfg: [tool:pitloom]: unknown key 'a\\nb' "
        "[config-unknown-key]"
    )


def test_an_unknown_key_hint_is_one_or_the_other() -> None:
    with pytest.raises(InternalError):
        warn_config_unknown_key(
            _LOG, _TOP, "x", file=None, setting="pretty", tables=(_TOP,)
        )


def test_the_hook_names_its_unknown_keys_sorted_and_escaped() -> None:
    exc = hook_unknown_keys(
        ConfigPlace("tool.hatch.build.hooks.pitloom"), {"z", "a\x1b"}
    )
    assert str(exc) == (
        "[tool.hatch.build.hooks.pitloom]: unknown keys 'a\\x1b', z; only enabled "
        "and Hatchling's own hook keys go here, other settings go in [tool.pitloom]"
    )
    assert raised_as(exc, CONFIG_UNKNOWN_KEY)


def test_recoded_keeps_the_text_and_code_in_another_class() -> None:
    missing = input_not_found("config file", "c.toml")
    assert isinstance(missing, CodedFileNotFoundError)
    again = recoded(CodedValueError, missing)
    assert isinstance(again, CodedValueError)
    assert not isinstance(again, FileNotFoundError)
    assert (str(again), code_of(again)) == (str(missing), "input-not-found")
    with pytest.raises(InternalError):
        recoded(CodedValueError, ValueError("plain"))


@pytest.mark.parametrize(
    "place",
    [ConfigPlace("tool.pitloom.creator", entry=0, sub="type"), _TOP.at("pretty")],
    ids=["entry-key", "key"],
)
def test_a_place_naming_a_key_takes_no_other(place: ConfigPlace) -> None:
    with pytest.raises(InternalError):
        place.at("name")


@pytest.mark.parametrize("name", [PurePosixPath("max_bytes"), "-x", "a b", 5])
def test_a_parameter_is_a_python_name_or_a_long_option_only(name: object) -> None:
    with pytest.raises(InternalError):
        Parameter(name)  # type: ignore[arg-type]


def test_a_backslash_found_is_shown_once() -> None:
    assert found_text("C:\\cfg") == "a string 'C:\\cfg'"
