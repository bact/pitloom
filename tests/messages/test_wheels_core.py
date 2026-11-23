# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The wheel lines' core (catalogue PR 16, step 1): every new line is a
well-formed template that renders from the drift samples; the refusal
constructors make a coded :class:`WheelRefused`, still a ``ValueError``;
the ``.dist-info`` and archive member helpers pick their entry and line;
and the readers that say them (``wheel_dist_info``,
``archive_member_names``, ``_wheel_sbom_location``) carry the codes.

See also: tests/messages/test_wheels_core_sboms.py (the embedded-SBOM
lines) and tests/messages/test_wheels_core_hostile.py (attacker text).
"""

from __future__ import annotations

import io
import logging
import pickle
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom._wheel_sbom_location import _find_dist_info_prefix, find_embedded_sbom
from pitloom.core.archive_member_names import archive_members, file_members
from pitloom.core.internal_error import InternalError
from pitloom.core.wheel_dist_info import (
    NotAWheelError,
    open_wheel_zip,
    read_metadata_headers,
    refuse_unreadable,
    resolve_own_dist_info,
    wheel_members,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    BUILD_FRAME,
    GIT_FRAME,
    MESSAGES,
    CodedValueError,
    Frame,
    code_of,
    topic_of,
    trusted_message,
)
from pitloom.messages import wheels as w
from pitloom.messages._templates import template_names
from pitloom.messages._types import template_problem
from tests._message_drift import SAMPLES

pytestmark = pytest.mark.platform  # ZIP archives, member names

_LOG = logging.getLogger("pitloom.core.wheel_dist_info")
_WHEEL = "demo-1.0-py3-none-any.whl"
_NEW = frozenset(
    {
        "wheel-unreadable",
        "wheel-invalid",
        "wheel-unusable",
        "wheel-unusable/signed",
        "dist-info-missing",
        "dist-info-ambiguous",
        "dist-info-conflict",
        "archive-member-unsafe",
        "archive-member-conflict",
        "archive-member-invalid",
        "wheel-sbom-missing",
        "wheel-sbom-ambiguous",
        "wheel-sbom-wrong-format",
        "wheel-sbom-unusable",
        "wheel-sbom-conflict",
        "wheel-sbom-conflict/held",
        "datetime-not-recordable",
        "sbom-name-conflict",
        "option-missing/project-dir",
        "json-malformed/bom",
        "file-unwritable/mode",
        "library-unusable/hatchling",
    }
)


def _zip(path: Path, *names: str, data: bytes = b"x") -> Path:
    """A ZIP archive at *path* holding *names*, each dated 1980 (no clock).

    ``ZipInfo`` turns a ``\\`` into ``/`` on Windows, so ``d/M`` and ``d\\M``
    are one name there and ``zipfile`` warns of the duplicate: it is the
    point of a test that writes both."""
    with zipfile.ZipFile(path, "w") as zf, warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Duplicate name", category=UserWarning
        )
        for name in names:
            zf.writestr(zipfile.ZipInfo(name), data)
    return path


def _said(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Each record as a printed line would end: ``LEVEL: text [code]``."""
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, CODE_ATTR)}]"
        for r in caplog.records
    ]


@pytest.mark.parametrize("code", sorted(_NEW))
def test_each_new_line_is_a_template_and_renders(code: str) -> None:
    message = MESSAGES[code]
    assert message.since == "0.25.0"
    for line in message.lines:
        assert template_problem(line.template) is None
        values = {name: SAMPLES[name] for name in template_names(line.template)}
        text = line.render(values)
        assert trusted_message(f"{line.level}: {text} [{code}]") is message


@pytest.mark.parametrize(
    ("family", "topic"),
    [
        ("wheel-invalid", "wheels"),
        ("dist-info-conflict", "wheels"),
        ("archive-member-unsafe", "wheels"),
        ("wheel-sbom-unusable", "wheel-sboms"),
        ("datetime-not-recordable", "wheel-sboms"),
        ("sbom-name-conflict", "wheel-sboms"),
    ],
)
def test_each_family_sits_on_its_page(family: str, topic: str) -> None:
    assert topic_of(family) == topic


def test_every_refusal_ends_wheel_refused() -> None:
    families = ("wheel-unreadable", "wheel-invalid", "wheel-unusable")
    for code, message in MESSAGES.items():
        for line in message.lines:
            if code.partition("/")[0] in families and line.level == "ERROR":
                assert line.template.endswith(f"; {w.WHEEL_REFUSED}"), code


_CONSTRUCTORS: list[tuple[Callable[[], w.WheelRefused], str, str]] = [
    (lambda: w.refuse_unopenable(_WHEEL, EOFError()), "wheel-unreadable", "(EOFError)"),
    (
        lambda: w.refuse_unreadable_member(_WHEEL, "a.py", zipfile.BadZipFile("x")),
        "wheel-unreadable",
        "(zipfile.BadZipFile)",
    ),
    (lambda: w.refuse_nul_name(_WHEEL, "a\0b"), "wheel-invalid", "NUL in member"),
    (lambda: w.refuse_duplicate_name(_WHEEL, "a"), "wheel-invalid", "duplicate"),
    (lambda: w.refuse_non_conforming(_WHEEL, "d\\M"), "wheel-unusable", "non-conf"),
    (
        lambda: w.refuse_signed(_WHEEL, "d/RECORD.jws"),
        "wheel-unusable/signed",
        "--allow-signed-wheel removes it",
    ),
    (lambda: w.refuse_dist_info(_WHEEL, w.DIST_INFO_NONE), "dist-info-missing", "no"),
    (
        lambda: w.refuse_dist_info(_WHEEL, w.DIST_INFO_SEVERAL_MATCH),
        "dist-info-ambiguous",
        "match the file name",
    ),
]


@pytest.mark.parametrize(
    ("make", "code", "text"), _CONSTRUCTORS, ids=[c for _, c, _ in _CONSTRUCTORS]
)
def test_a_refusal_is_a_coded_value_error(
    make: Callable[[], w.WheelRefused], code: str, text: str
) -> None:
    exc = make()
    assert isinstance(exc, ValueError) and isinstance(exc, CodedValueError)
    assert code_of(exc) == code and text in str(exc)
    assert trusted_message(f"ERROR: {exc} [{code}]") is MESSAGES[code]
    copied = pickle.loads(pickle.dumps(exc))
    assert copied.__class__ is w.WheelRefused and str(copied) == str(exc)
    assert code_of(copied) == code


def test_a_refusal_names_the_type_never_the_text() -> None:
    exc = w.refuse_unopenable(Path("/abs/dir") / _WHEEL, OSError("secret 'a.py'"))
    assert str(exc) == (
        f"ARCHIVE='{_WHEEL}': could not open as a ZIP archive (OSError); wheel refused"
    )


def test_not_a_wheel_is_still_a_wheel_refusal() -> None:
    assert issubclass(NotAWheelError, w.WheelRefused)
    with pytest.raises(w.WheelRefused) as caught:
        open_wheel_zip(Path("demo.zip"))
    assert code_of(caught.value) == "target-wrong-format"


@pytest.mark.parametrize("problem", [w.DIST_INFO_OTHER, "nope"])
def test_refuse_dist_info_takes_an_unchosen_problem_only(problem: str) -> None:
    with pytest.raises(InternalError):
        w.refuse_dist_info(_WHEEL, problem)


@pytest.mark.parametrize(
    ("problem", "chosen", "code", "tail"),
    [
        (
            w.DIST_INFO_OTHER,
            "d.dist-info/",
            "dist-info-conflict",
            "using 'd.dist-info/'",
        ),
        (w.DIST_INFO_NONE, None, "dist-info-missing", "; identity unknown"),
        (w.DIST_INFO_NOT_A_WHEEL_NAME, None, "dist-info-ambiguous", "unknown"),
        (w.DIST_INFO_SEVERAL_NONE_MATCH, None, "dist-info-ambiguous", "unknown"),
    ],
)
def test_warn_dist_info_picks_its_line(
    caplog: pytest.LogCaptureFixture,
    problem: str,
    chosen: str | None,
    code: str,
    tail: str,
) -> None:
    w.warn_dist_info(_LOG, _WHEEL, problem, chosen=chosen)
    (line,) = _said(caplog)
    assert line.startswith(f"WARNING: ARCHIVE='{_WHEEL}': ")
    assert line.endswith(f"{tail} [{code}]") and trusted_message(line)


@pytest.mark.parametrize(
    ("problem", "chosen"), [(w.DIST_INFO_OTHER, None), (w.DIST_INFO_NONE, "d/")]
)
def test_warn_dist_info_refuses_a_wrong_choice(
    problem: str, chosen: str | None
) -> None:
    with pytest.raises(InternalError):
        w.warn_dist_info(_LOG, _WHEEL, problem, chosen=chosen)


@pytest.mark.parametrize(
    ("names", "problem"),
    [
        (["demo-1.0.dist-info/METADATA"], None),
        (["other-2.0.dist-info/METADATA"], w.DIST_INFO_OTHER),
        (["a.py"], w.DIST_INFO_NONE),
        (["demo-1.0.dist-info/M", "Demo-1.0.dist-info/M"], w.DIST_INFO_SEVERAL_MATCH),
        (["a-1.dist-info/M", "b-1.dist-info/M"], w.DIST_INFO_SEVERAL_NONE_MATCH),
    ],
)
def test_resolve_own_dist_info_returns_a_problem_id(
    names: list[str], problem: str | None
) -> None:
    assert resolve_own_dist_info(_WHEEL, names).problem == problem
    assert problem is None or problem in w.DIST_INFO_PROBLEMS


def test_a_renamed_file_with_several_dist_infos_is_not_a_wheel_name() -> None:
    names = ["a-1.dist-info/M", "b-1.dist-info/M"]
    assert resolve_own_dist_info("x.whl", names).problem == w.DIST_INFO_NOT_A_WHEEL_NAME


def test_a_nul_member_name_refuses_the_wheel(tmp_path: Path) -> None:
    path = _zip(tmp_path / _WHEEL, "aXb.py")
    raw = path.read_bytes().replace(b"aXb.py", b"a\0b.py")
    assert raw != path.read_bytes()  # the name really changed
    path.write_bytes(raw)
    with zipfile.ZipFile(path) as zf, pytest.raises(w.WheelRefused) as caught:
        wheel_members(zf, _WHEEL)
    assert code_of(caught.value) == "wheel-invalid"
    assert "ENTRY='a\\x00b.py': NUL in member name; wheel refused" in str(caught.value)


def test_a_duplicate_member_name_refuses_the_wheel(tmp_path: Path) -> None:
    path = _zip(tmp_path / _WHEEL, "d/M", "d\\M")
    with zipfile.ZipFile(path) as zf, pytest.raises(w.WheelRefused) as caught:
        wheel_members(zf, _WHEEL)
    assert str(caught.value).endswith(
        "ENTRY='d/M': duplicate member name; wheel refused"
    )


def test_a_file_that_is_not_a_zip_is_unreadable(tmp_path: Path) -> None:
    path = tmp_path / _WHEEL
    path.write_bytes(b"not a zip")
    with pytest.raises(w.WheelRefused) as caught:
        open_wheel_zip(path)
    assert code_of(caught.value) == "wheel-unreadable"
    assert "(zipfile.BadZipFile); wheel refused" in str(caught.value)


def test_a_member_read_failure_is_unreadable() -> None:
    with pytest.raises(w.WheelRefused) as caught, refuse_unreadable(_WHEEL, "d/M"):
        raise EOFError("cut short at 'd/M'")
    assert str(caught.value) == (
        f"ARCHIVE='{_WHEEL}' ENTRY='d/M': could not read (EOFError); wheel refused"
    )


def test_a_missing_metadata_says_dist_info_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _zip(tmp_path / _WHEEL, "demo-1.0.dist-info/RECORD")
    with zipfile.ZipFile(path) as zf:
        members = wheel_members(zf, _WHEEL)
        assert read_metadata_headers(zf, members, "demo-1.0.dist-info/", _WHEEL) is None
        assert not read_metadata_headers(
            zf, members, "demo-1.0.dist-info/", _WHEEL, report=False
        )
    (line,) = _said(caplog)
    assert line == (
        f"WARNING: ARCHIVE='{_WHEEL}' ENTRY='demo-1.0.dist-info/METADATA': not in "
        "the wheel; identity unknown [dist-info-missing]"
    )


def test_the_location_refuses_and_warns_by_problem(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    other = _zip(tmp_path / _WHEEL, "other-2.0.dist-info/METADATA")
    with zipfile.ZipFile(other) as zf:
        assert _find_dist_info_prefix(zf, other, report=True) == "other-2.0.dist-info/"
        assert _find_dist_info_prefix(zf, other) == "other-2.0.dist-info/"
    (line,) = _said(caplog)
    assert line.endswith("using 'other-2.0.dist-info/' [dist-info-conflict]")
    bare = _zip(tmp_path / "bare-1.0-py3-none-any.whl", "a.py")
    with zipfile.ZipFile(bare) as zf, pytest.raises(w.WheelRefused) as caught:
        _find_dist_info_prefix(zf, bare)
    assert code_of(caught.value) == "dist-info-missing"


def test_several_embedded_sboms_are_ambiguous(tmp_path: Path) -> None:
    path = _zip(
        tmp_path / _WHEEL,
        "demo-1.0.dist-info/METADATA",
        "demo-1.0.dist-info/sboms/b.json",
        "demo-1.0.dist-info/sboms/a.spdx3.json",
    )
    with pytest.raises(CodedValueError) as caught:
        find_embedded_sbom(path)
    assert str(caught.value) == (
        f"ARCHIVE='{_WHEEL}': 2 SBOMs under .dist-info/sboms/ "
        "('demo-1.0.dist-info/sboms/a.spdx3.json', "
        "'demo-1.0.dist-info/sboms/b.json'); pass --sbom-filename"
    )
    assert code_of(caught.value) == "wheel-sbom-ambiguous"


_MEMBERS = [
    ("/abs.py", 0),
    ("d/a.py", 0),
    ("d\\a.py", 0),
    ("f", 0),
    ("f/g.py", 0),
    ("x//y.py", 0),
    ("e/", 3),
]


@pytest.mark.parametrize(
    ("frame", "outcome", "renamed"),
    [(None, "not listed", "listed as"), (BUILD_FRAME, "not copied", "copied as")],
    ids=["read", "build"],
)
def test_each_member_kind_says_its_line(
    caplog: pytest.LogCaptureFixture, frame: Frame | None, outcome: str, renamed: str
) -> None:
    entries = [(raw, size, raw) for raw, size in _MEMBERS]
    kept = file_members(entries, _WHEEL, _LOG, frame)
    assert [name for name, _ in kept] == ["d/a.py", "f/g.py", "x/y.py"]
    head = "Build: " if frame is BUILD_FRAME else ""
    arc = f"{head}ARCHIVE='{_WHEEL}'"
    assert _said(caplog) == [
        f"WARNING: {arc} ENTRY='e/': directory entry carries data; {outcome} "
        "[archive-member-invalid]",
        f"WARNING: {arc} ENTRY='/abs.py': no safe install location; {outcome} "
        "[archive-member-unsafe]",
        f"WARNING: {arc} ENTRY='d/a.py': overwritten by later entry 'd\\a.py'; "
        f"{outcome} [archive-member-conflict]",
        f"WARNING: {arc} ENTRY='d\\a.py': non-conforming name; {renamed} 'd/a.py' "
        "[archive-member-invalid]",
        f"WARNING: {arc} ENTRY='f': also a directory of other entries; {outcome} "
        "[archive-member-conflict]",
        f"WARNING: {arc} ENTRY='x//y.py': non-conforming name; {renamed} 'x/y.py' "
        "[archive-member-invalid]",
    ]
    assert all(trusted_message(line) for line in _said(caplog))


def test_a_second_read_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    assert not archive_members([("/abs.py", 1)], _WHEEL, None)
    assert not caplog.records


@pytest.mark.parametrize(
    ("kind", "frame", "later", "listed_as"),
    [
        ("nope", None, None, None),
        (w.MEMBER_OUTSIDE, None, None, None),
        (w.MEMBER_UNSAFE, GIT_FRAME, None, None),
        (w.MEMBER_OVERWRITTEN, None, None, None),
        (w.MEMBER_UNSAFE, None, "b", None),
        (w.MEMBER_NORMALISED, None, None, None),
        (w.MEMBER_UNSAFE, None, None, "b"),
    ],
    ids=["kind", "outside-read", "frame", "no-later", "later", "no-name", "name"],
)
def test_warn_archive_member_refuses_a_wrong_call(
    kind: str, frame: Frame | None, later: str | None, listed_as: str | None
) -> None:
    with pytest.raises(InternalError):
        w.warn_archive_member(
            _LOG, kind, _WHEEL, "a", frame=frame, later=later, listed_as=listed_as
        )


def test_outside_is_the_build_routes_line(caplog: pytest.LogCaptureFixture) -> None:
    w.warn_archive_member(_LOG, w.MEMBER_OUTSIDE, _WHEEL, "l/x", frame=BUILD_FRAME)
    (line,) = _said(caplog)
    assert line == (
        f"WARNING: Build: ARCHIVE='{_WHEEL}' ENTRY='l/x': resolves outside the "
        "extraction directory; not copied [archive-member-unsafe]"
    )
    assert trusted_message(line)


def test_shared_paths_show_ten_then_a_count(caplog: pytest.LogCaptureFixture) -> None:
    w.warn_shared_paths(_LOG, Path("/d/demo-1.0.tar.gz"), [f"p{i}" for i in range(12)])
    (line,) = _said(caplog)
    shown = ", ".join(f"'p{i}'" for i in range(10))
    assert line == (
        f"WARNING: ARCHIVE='demo-1.0.tar.gz': members share a project path "
        f"({shown} and 2 more); they would share one ID registry key "
        "[archive-member-conflict]"
    )
    with pytest.raises(InternalError):
        w.warn_shared_paths(_LOG, _WHEEL, [])


def test_the_signature_note_is_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    w.say_signature_removed(_LOG, _WHEEL, "d/RECORD.jws")
    (line,) = _said(caplog)
    assert line.startswith("INFO: ") and "signature removed; re-sign" in line
    assert trusted_message(line) is MESSAGES["wheel-unusable/signed"]


def test_the_exception_label_writer_refuses_text() -> None:
    assert w.exception_label(zipfile.BadZipFile()) == "zipfile.BadZipFile"
    with pytest.raises(ValueError, match="not an exception"):
        w.UNOPENABLE_LINE.render({"archive": _WHEEL, "exception_type": "EOFError"})


def test_the_archive_writer_names_a_path_by_its_last_part() -> None:
    line = w.NO_DIST_INFO_LINE
    assert line.render({"archive": Path("/a/b") / _WHEEL}).startswith(
        f"ARCHIVE='{_WHEEL}':"
    )
    with pytest.raises(ValueError):
        line.render({"archive": io.BytesIO()})
