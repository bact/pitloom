# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SBOM fragment entries and their core: the lines and their shapes, the
fields only they name, the reader's stage classifier
(:class:`~pitloom.messages.fragments.FragmentReadError`), the say-helpers,
and the coded merge errors (``fragment-missing``, ``reference-not-found``)
through :func:`~pitloom.assemble.spdx3.fragments.merge_fragments` and
:func:`~pitloom.assemble.generate_merged_sbom`.

See also: tests/core/test_fragments_read.py (the reader through the
surfaces) and tests/messages/test_input_not_found.py
(``input-not-found/fragment``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pytest

from pitloom.assemble import generate_merged_sbom
from pitloom.assemble.spdx3 import _fragments_read
from pitloom.assemble.spdx3._fragments_read import parse_fragment, read_fragment_set
from pitloom.assemble.spdx3.fragments import FragmentMergeError, merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.internal_error import InternalError
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.logging_config import EXCERPT_CHARS, configure_logging
from pitloom.messages import (
    FIELDS,
    MESSAGES,
    SUMMARIES,
    Line,
    Message,
    code_of,
    topic_of,
    trusted_message,
)
from pitloom.messages._types import template_problem
from pitloom.messages.fragments import (
    FRAGMENT_MISSING,
    MERGE_WILL_FAIL,
    NOT_MERGED,
    READ_STAGES,
    SHOWN_FILES,
    DescribedValue,
    FragmentReadError,
    missing_files_text,
    warn_fragment_unread,
    warn_id_conflict,
    warn_property_conflict,
)
from pitloom.messages.targets import INPUT_NOT_FOUND_FRAGMENT
from tests._message_drift import SAMPLES

pytestmark = pytest.mark.platform

_FAMILIES = frozenset(
    {
        "datetime-missing",
        "fragment-conflict",
        "fragment-digest-invalid",
        "fragment-hash-conflict",
        "fragment-id-conflict",
        "fragment-invalid",
        "fragment-missing",
        "fragment-unreadable",
        "fragment-unusable",
        "generated-value-conflict",
        "reference-not-found",
    }
)
_ENTRIES = [m for m in MESSAGES.values() if m.family in _FAMILIES]
_NEW_FIELDS = (
    "datetime",
    "digest",
    "entry_key",
    "hash_algorithm",
    "holder_type",
    "new_id",
    "other_digest",
    "property",
    "provenance_field",
    "reference",
)
_AGENT = "https://e.org/a#A"


def _fragment(**extra: object) -> dict[str, object]:
    """A fragment holding one agent, plus *extra* top-level keys."""
    return {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "CreationInfo",
                "@id": "_:c",
                "specVersion": "3.0.1",
                "created": "2024-01-01T00:00:00Z",
                "createdBy": [_AGENT],
            },
            {
                "type": "SoftwareAgent",
                "spdxId": _AGENT,
                "name": "x",
                "creationInfo": "_:c",
            },
        ],
        **extra,
    }


def _printed(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Each record of *caplog* as the command line prints it."""
    return [
        f"{r.levelname}: {r.getMessage()} [{getattr(r, 'pitloom_code', '')}]"
        for r in caplog.records
    ]


# -- the entries ---------------------------------------------------------------


def test_every_family_is_on_the_fragments_page_since_0_25_0() -> None:
    assert {m.family for m in _ENTRIES} == _FAMILIES
    assert {topic_of(m.code) for m in _ENTRIES} == {"fragments"}
    assert {m.since for m in _ENTRIES} == {"0.25.0"}
    fragment_summaries = [s for s in SUMMARIES if s.topic == "fragments"]
    assert len(fragment_summaries) == 4


@pytest.mark.parametrize(
    ("message", "line"),
    [(m, ln) for m in _ENTRIES for ln in m.lines],
    ids=[f"{m.code}-{i}" for m in _ENTRIES for i, _ in enumerate(m.lines)],
)
def test_every_line_passes_the_template_rules_and_reads_back(
    message: Message, line: Line
) -> None:
    assert template_problem(line.template) is None
    assert line.template.isascii() and message.advice.isascii()
    text = line.render({n: SAMPLES[n] for n in line.fields})
    assert trusted_message(f"{line.level}: {text} [{message.code}]") is message


def test_a_required_twin_differs_from_its_line_only_in_the_outcome() -> None:
    pairs = 0
    for message in (*_ENTRIES, INPUT_NOT_FOUND_FRAGMENT):
        templates = {ln.template for ln in message.lines}
        for template in templates:
            if template.endswith(f"; {NOT_MERGED}"):
                head = template.removesuffix(NOT_MERGED)
                assert f"{head}{MERGE_WILL_FAIL}" in templates
                pairs += 1
    assert pairs == 5  # unreadable, invalid twice, unusable, not found
    assert INPUT_NOT_FOUND_FRAGMENT.subject_key == "FILE"


@pytest.mark.parametrize("name", _NEW_FIELDS)
def test_every_new_field_writes_its_sample_in_its_shape(name: str) -> None:
    field = FIELDS[name]
    assert re.fullmatch(field.pattern, field.write(SAMPLES[name])) is not None


@pytest.mark.parametrize(
    ("given", "written"),
    [("from_", "from"), ("import_", "import"), ("description", "description")],
)
def test_a_property_is_named_as_the_document_names_it(given: str, written: str) -> None:
    assert FIELDS["property"].write(given) == written


def test_a_described_value_is_not_quoted_and_a_text_is() -> None:
    kept = FIELDS["kept"]
    assert kept.write("abc") == "'abc'"
    assert (
        kept.write(DescribedValue("Hash(algorithm=sha256)")) == "Hash(algorithm=sha256)"
    )


def test_a_long_described_value_is_masked_cut_and_on_one_line() -> None:
    value = DescribedValue("https://u:s3cret@h.example/\n" + "x" * 10_000)
    written = FIELDS["dropped"].write(value)
    assert "s3cret" not in written and "\n" not in written
    assert written.endswith("...") and len(written) <= EXCERPT_CHARS + 10


def test_a_value_not_described_is_an_internal_error() -> None:
    log = logging.getLogger("pitloom.test_fragments")
    with pytest.raises(InternalError, match="DescribedValue"):
        warn_property_conflict(
            log,
            spdx_id="x#a",
            prop="name",
            kept="a",
            dropped=3,  # type: ignore[arg-type]
        )


def test_id_conflict_picks_its_line_by_the_algorithm(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging()
    log = logging.getLogger("pitloom.assemble.x")
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        for algorithm in (None, "sha256"):
            warn_id_conflict(
                log,
                spdx_id="https://e.org/a#F",
                element_type="software_File",
                holder_type="software_Package",
                new_id="https://e.org/a#File-2",
                hash_algorithm=algorithm,
            )
    first, second = caplog.messages
    assert "'software_Package'" in first and "sha256" not in first
    assert "different sha256 digests" in second
    assert all(trusted_message(line) for line in _printed(caplog))


def test_missing_files_are_listed_in_order_up_to_the_cap() -> None:
    names = [f"f{i}.json" for i in range(SHOWN_FILES + 2)]
    text = missing_files_text(names)
    assert text.startswith("f0.json, f1.json")
    assert text.endswith(f"f{SHOWN_FILES - 1}.json and 2 more")
    assert missing_files_text(["b.json", "a.json"]) == "b.json, a.json"
    with pytest.raises(InternalError):
        missing_files_text([])


# -- the reader's stages ------------------------------------------------------


def test_an_unknown_stage_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        raise FragmentReadError("parse", ValueError("x"))
    assert set(READ_STAGES) == {"read", "json", "spdx"}


@pytest.mark.parametrize(
    ("raw", "stage"),
    [
        (b"{not json", "json"),
        ("{}".encode("utf-16")[:-1], "json"),
        (b"[" * 100_000 + b"]" * 100_000, "json"),
        (b"3", "spdx"),
        (b'{"a": 1}', "spdx"),
        (json.dumps(_fragment(big=2**60)).encode(), "spdx"),
        (
            json.dumps(_fragment()).replace("SoftwareAgent", "NoSuchType").encode(),
            "spdx",
        ),
    ],
    ids=[
        "syntax",
        "utf16-cut",
        "deep",
        "number",
        "untyped",
        "big-integer",
        "unknown-type",
    ],
)
def test_each_failure_is_tagged_with_the_stage_that_raised_it(
    raw: bytes, stage: str
) -> None:
    with pytest.raises(FragmentReadError) as raised:
        parse_fragment(raw, file="f.json")
    assert raised.value.stage == stage
    assert "\n" not in str(raised.value)


def test_a_utf8_bom_and_utf16_fragment_parse() -> None:
    body = json.dumps(_fragment())
    for raw in (b"\xef\xbb\xbf" + body.encode(), body.encode("utf-16")):
        assert parse_fragment(raw, file="f.json").objects.objects


def test_a_file_that_cannot_be_read_is_the_read_stage(tmp_path: Path) -> None:
    with pytest.raises(FragmentReadError) as raised:
        read_fragment_set(tmp_path)  # a directory
    assert raised.value.stage == "read"


@pytest.mark.parametrize(
    "error", [MemoryError(), InternalError("bug")], ids=["memory", "internal"]
)
@pytest.mark.parametrize("where", ["json", "rfc8785"])
def test_memory_and_internal_errors_are_never_wrapped(
    error: BaseException, where: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise error

    if where == "json":
        monkeypatch.setattr(_fragments_read, "escape_lone_surrogates_in", boom)
    else:
        monkeypatch.setattr("rfc8785.dumps", boom)
    with pytest.raises(type(error)):
        parse_fragment(json.dumps(_fragment()).encode(), file="f.json")


@pytest.mark.parametrize("required", [False, True], ids=["optional", "required"])
@pytest.mark.parametrize(
    ("stage", "code", "words"),
    [
        ("read", "fragment-unreadable", "could not be read"),
        ("json", "fragment-invalid", "not valid JSON"),
        ("spdx", "fragment-invalid", "not SPDX 3 JSON-LD"),
    ],
)
def test_each_stage_says_its_line(
    stage: str, code: str, words: str, required: bool, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging()
    log = logging.getLogger("pitloom.assemble.x")
    exc = FragmentReadError(stage, PermissionError(13, "Permission denied", "/abs/x"))
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_fragment_unread(log, "frags/x.json", exc, required=required)
    (line,) = _printed(caplog)
    assert line.startswith("WARNING: FILE=frags/x.json: ") and words in line
    assert line.endswith(f"; {MERGE_WILL_FAIL if required else NOT_MERGED} [{code}]")
    assert "/abs/x" not in line and trusted_message(line) is MESSAGES[code]


# -- the merge errors ---------------------------------------------------------


def test_required_fragments_not_merged_raise_fragment_missing_in_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bad.json").write_bytes(b"{not json")
    frags = [
        FragmentConfig(path="z-missing.json", required=True),
        FragmentConfig(path="bad.json", required=True),
        FragmentConfig(path="gone.json"),
    ]
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError) as raised:
            merge_fragments(tmp_path, frags, Spdx3JsonExporter())
    assert code_of(raised.value) == FRAGMENT_MISSING.code
    assert str(raised.value).startswith(
        "2 required SBOM fragment(s) not merged: z-missing.json, bad.json; "
    )
    assert isinstance(raised.value, ValueError)
    assert [r.pitloom_code for r in caplog.records] == [  # type: ignore[attr-defined]
        "input-not-found/fragment",
        "fragment-invalid",
        "input-not-found/fragment",
    ]


def _dangling_fragment(path: Path, count: int) -> None:
    """A fragment of *count* relationships, each to a missing element."""
    doc = _fragment()
    graph = doc["@graph"]
    assert isinstance(graph, list)
    for i in reversed(range(count)):
        graph.append(
            {
                "type": "Relationship",
                "spdxId": f"https://e.org/a#r{i}",
                "creationInfo": "_:c",
                "from": _AGENT,
                "relationshipType": "other",
                "to": [f"https://e.org/a#gone{i}"],
            }
        )
    path.write_bytes(json.dumps(doc).encode())


def test_dangling_references_are_said_sorted_and_raise_coded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _dangling_fragment(tmp_path / "d.json", 6)
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError) as raised:
            generate_merged_sbom(tmp_path, output_path=tmp_path / "out.json")
    assert code_of(raised.value) == "reference-not-found"
    assert str(raised.value).startswith("6 reference(s) to elements not in")
    ids = []
    for record in caplog.records:
        found = re.search(r"ELEMENT=(\S+): ", record.getMessage())
        assert found is not None
        ids.append(found.group(1))
    assert ids == sorted(ids) and len(ids) == 6
    assert not (tmp_path / "out.json").exists()


def test_loom_merge_of_only_bad_fragments_writes_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    frags = tmp_path / "frags"
    frags.mkdir()
    (frags / "a.json").write_bytes(b"{not json")
    (frags / "b.json").write_bytes(b'{"a": 1}')
    out = tmp_path / "out.json"
    counted: list[int] = []
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with pytest.raises(FragmentMergeError) as raised:
            generate_merged_sbom(frags, output_path=out, on_merged=counted.append)
    assert code_of(raised.value) == FRAGMENT_MISSING.code
    assert str(raised.value).startswith("no SBOM fragment in ")
    assert not out.exists() and not counted
    assert not any("creation time" in m for m in caplog.messages)
    shown = [r.getMessage().split(":")[0] for r in caplog.records]
    assert shown == [f"FILE={frags / 'a.json'}", f"FILE={frags / 'b.json'}"]


def test_loom_merge_counts_merged_fragments_only(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_bytes(json.dumps(_fragment()).encode())
    (tmp_path / "b.json").write_bytes(json.dumps(_fragment()).encode())
    (tmp_path / "c.json").write_bytes(b"{not json")
    counted: list[int] = []
    generate_merged_sbom(
        tmp_path, output_path=tmp_path / "out", on_merged=counted.append
    )
    assert counted == [2]


@pytest.mark.parametrize(
    ("graph", "epoch", "said"),
    [([], None, True), ([], "1700000000", False), (None, None, False)],
    ids=["no-created", "source-date-epoch", "fragment-created"],
)
def test_a_merge_with_no_creation_time_says_datetime_missing_once(
    graph: list[object] | None,
    epoch: str | None,
    said: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1970 and one ``datetime-missing`` only when neither
    ``SOURCE_DATE_EPOCH`` nor a fragment's ``created`` dates the merge."""
    if epoch is None:
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    else:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", epoch)
    fragment = _fragment() if graph is None else {"@graph": graph}
    (tmp_path / "f.json").write_bytes(json.dumps(fragment).encode())
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        sbom = generate_merged_sbom(tmp_path, output_path=tmp_path / "out")
    codes = [getattr(r, "pitloom_code", None) for r in caplog.records]
    assert codes == (["datetime-missing"] if said else [])
    assert ("1970-01-01T00:00:00Z" in sbom) is said
    if said:
        assert all(trusted_message(line) for line in _printed(caplog))
