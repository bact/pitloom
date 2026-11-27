# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Boundaries and orders of the wheel and embed messages that mutation
testing found unpinned (catalogue PR 16): the display cuts, the name
masking order, each ``.dist-info`` refusal's own line, the order of
cross-check gaps, an empty ``--sbom-filename``, the hatch name clash, and a
wheel reached through a link named as given.

See also: tests/messages/test_wheels_core*.py (the messages themselves).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom._wheel_sbom_location import find_embedded_sbom
from pitloom.core.url_masking import CHECKOUT_DIR_PREFIX
from pitloom.embed import embed_sbom_in_wheel
from pitloom.messages import code_of
from pitloom.messages import wheel_sboms as s
from pitloom.messages import wheels as w
from pitloom.messages._compared_value import (
    ComparedValue,
    compared_pair,
    compared_text,
)
from pitloom.messages._field_writers import cut_name
from pitloom.messages._sbom_validation_say import (
    relay_validator_text,
    say_validation_findings,
)
from tests._symlink import CAN_SYMLINK
from tests._wheel_fixtures import (
    WHEEL_FILE,
    make_wheel,
    metadata,
    spdx3_sbom,
    write_wheel,
)
from tests.extract.conftest import make_hook

pytestmark = pytest.mark.platform  # ZIP archives, links, member names

_LOG = logging.getLogger("pitloom.test_mutation_gaps")


# -- cut boundaries: 500 characters for a name, 120 for a value --------------


def test_a_name_is_cut_past_500_characters_only() -> None:
    assert cut_name("a" * 500) == "a" * 500
    assert cut_name("a" * 501) == "a" * 500 + "..."


def test_a_name_is_masked_before_it_is_cut() -> None:
    shown = cut_name("a" * 485 + "https://user:secret@host/p/q")
    assert "user" not in shown and "secret" not in shown


def test_a_name_has_its_checkout_and_its_secret_parameter_masked() -> None:
    assert cut_name(f"/tmp/{CHECKOUT_DIR_PREFIX}v6mrrlyz/x.whl") == "<checkout>/x.whl"
    assert "SECRET" not in cut_name("a?access_token=SECRET")


def test_a_compared_value_is_cut_past_120_characters_only() -> None:
    assert compared_text("x" * 120) == "'" + "x" * 120 + "'"
    assert compared_text("x" * 121) == "'" + "x" * 120 + "...'"


def test_values_differing_only_past_the_cut_say_where() -> None:
    past = ("x" * 120 + "a", "x" * 120 + "b")
    assert compared_pair(*past) == (
        ComparedValue(past[0], 120),
        ComparedValue(past[1], 120),
    )
    inside = ("x" * 119 + "a" + "z", "x" * 119 + "b" + "z")
    assert compared_pair(*inside) == inside


def test_the_rest_after_a_difference_is_cut_past_120_characters_only() -> None:
    whole = compared_text(ComparedValue("x" * 10 + "y" * 120, 10))
    assert whole.endswith(f"(from character 11: '{'y' * 120}')")
    cut = compared_text(ComparedValue("x" * 10 + "y" * 121, 10))
    assert cut.endswith(f"(from character 11: '{'y' * 120}'...)")


def test_a_value_that_is_not_text_is_shown_as_sorted_ascii_json() -> None:
    assert compared_text(["é"]) == "'[\"\\\\u00e9\"]'"
    assert compared_text({"b": 1, "a": 2}) == '\'{"a": 2, "b": 1}\''


# -- the validator relay ------------------------------------------------------


def test_a_relayed_line_is_cut_past_1000_characters_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    relay_validator_text("x" * 1000)
    relay_validator_text("x" * 1001)
    first, second = capsys.readouterr().err.splitlines()
    assert first == "ERROR: spdx3-validate: " + "x" * 1000
    assert second == "ERROR: spdx3-validate: " + "x" * 1000 + "..."


def test_the_findings_said_are_counted_not_the_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    findings = [("a.json", "k", f"m{i}") for i in range(3)]
    assert say_validation_findings(findings) == 3
    assert capsys.readouterr().err.count("spdx3-validate: ") == 3


# -- each refusal and gap says its own cause, in order ------------------------


@pytest.mark.parametrize(
    ("problem", "text"),
    [
        (w.DIST_INFO_NONE, "no top-level .dist-info directory"),
        (w.DIST_INFO_SEVERAL_MATCH, "directories match the file name"),
        (w.DIST_INFO_NOT_A_WHEEL_NAME, "the file name is not a wheel name"),
        (w.DIST_INFO_SEVERAL_NONE_MATCH, "none the one the file name names"),
    ],
    ids=["none", "several-match", "not-a-wheel-name", "several-none-match"],
)
def test_each_dist_info_problem_refuses_with_its_own_line(
    problem: str, text: str
) -> None:
    refused = w.refuse_dist_info("x.whl", problem)
    assert text in str(refused) and str(refused).endswith("; wheel refused")


def test_cross_check_gaps_are_said_in_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gaps = [
        s.CrossCheckGap(s.GAP_WHEEL_PART_MISSING, part="name"),
        s.CrossCheckGap(s.GAP_SBOM_PART_MISSING, part="version"),
    ]
    with caplog.at_level(logging.WARNING):
        s.warn_cross_check_gaps(_LOG, "w.whl", gaps)
    said = [r.getMessage() for r in caplog.records]
    assert "name" in said[0] and "wheel" in said[0]
    assert "version" in said[1] and "SBOM" in said[1]


def test_an_empty_sbom_filename_is_a_name_not_an_absent_one() -> None:
    assert "named ''" in str(s.wheel_sbom_missing("w.whl", ""))
    assert "named" not in str(s.wheel_sbom_missing("w.whl", None))


def test_an_empty_sbom_filename_is_refused(tmp_path: Path) -> None:
    """``""`` is no request for the one SBOM (``None`` is): refused before the
    wheel is read, as ``--sbom-filename ''`` is."""
    wheel = make_wheel(tmp_path, sboms={"one.spdx3.json": spdx3_sbom()})
    with pytest.raises(ValueError) as caught:
        find_embedded_sbom(wheel, "")
    assert code_of(caught.value) == "option-invalid"
    found = find_embedded_sbom(wheel)
    assert found is not None and found.arcname.endswith("one.spdx3.json")


def test_a_sbom_file_name_clash_ignores_the_case_of_the_staged_name(
    tmp_path: Path,
) -> None:
    hook = make_hook(str(tmp_path), {})
    with pytest.raises(ValueError) as caught:
        hook._check_name_is_free(  # pylint: disable=protected-access
            "MINE.spdx3.json", {"sbom_files": ["mine.spdx3.json"]}
        )
    assert code_of(caught.value) == "sbom-name-conflict"


# -- a wheel reached through a link is named as given, never by its target ----

_NEEDS_LINK = pytest.mark.skipif(not CAN_SYMLINK, reason="needs a symbolic link")


def _link_to(real: Path, directory: Path, name: str = WHEEL_FILE) -> Path:
    link = directory / "link" / name
    link.parent.mkdir()
    link.symlink_to(real)
    return link


def _linked_refusal(link: Path) -> str:
    with pytest.raises(ValueError) as caught:
        embed_sbom_in_wheel(link, spdx3_sbom(), sbom_filename="x.spdx3.json")
    return str(caught.value)


@_NEEDS_LINK
def test_a_signed_wheel_through_a_link_is_refused_by_the_links_name(
    tmp_path: Path,
) -> None:
    real = make_wheel(
        tmp_path / "real",
        name="target",
        extra={"target-1.0.dist-info/RECORD.jws": b"s"},
    )
    link = _link_to(real, tmp_path)
    assert _linked_refusal(link).startswith(f"ARCHIVE='{WHEEL_FILE}' ENTRY=")


@_NEEDS_LINK
def test_duplicate_members_through_a_link_are_refused_by_the_links_name(
    tmp_path: Path,
) -> None:
    real = write_wheel(
        tmp_path / "real" / "target-1.0-py3-none-any.whl",
        {
            "target-1.0.dist-info/METADATA": metadata("target"),
            "p/m.py": b"1",
            "p\\m.py": b"2",
        },
    )
    link = _link_to(real, tmp_path)
    assert _linked_refusal(link).startswith(f"ARCHIVE='{WHEEL_FILE}' ENTRY=")


@_NEEDS_LINK
def test_a_damaged_member_through_a_link_is_refused_by_the_links_name(
    tmp_path: Path,
) -> None:
    real = make_wheel(tmp_path / "real", name="target", extra={"p/data.bin": b"abcdef"})
    data = real.read_bytes()
    assert b"abcdef" in data
    real.write_bytes(data.replace(b"abcdef", b"abcdeg"))  # the CRC no longer holds
    link = _link_to(real, tmp_path)
    assert _linked_refusal(link).startswith(
        f"ARCHIVE='{WHEEL_FILE}' ENTRY='p/data.bin'"
    )


@_NEEDS_LINK
def test_the_dist_info_is_picked_by_the_links_name(tmp_path: Path) -> None:
    members = {
        f"{n}-{v}.dist-info/{f}": data
        for n, v in (("a", "1.0"), ("b", "2.0"))
        for f, data in (("METADATA", metadata(n, v)), ("RECORD", b""))
    }
    real = write_wheel(tmp_path / "real" / "b-2.0-py3-none-any.whl", members)
    link = _link_to(real, tmp_path, "a-1.0-py3-none-any.whl")
    _, arcname, _, _ = embed_sbom_in_wheel(
        link, spdx3_sbom("a", "1.0"), sbom_filename="x.spdx3.json"
    )
    assert arcname == "a-1.0.dist-info/sboms/x.spdx3.json"
