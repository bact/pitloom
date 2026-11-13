# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message reference (the index ``docs/message-codes.md`` and each skill's
``references/messages.md``, with one page per topic beside it) and the model
table of the enrich skill's ``model-stub-diagnosis.md`` are generated from the
catalogue by ``scripts/generate_message_reference.py``: the files hold exactly
what the script renders (bytes, LF), the script rewrites only an index's block,
and a page has a section per code that says every line of it, in Markdown that
lints clean (no line over 80 characters outside a table or a code block, none
that starts with ``<``).

See also: tests/messages/test_drift_quotes.py (quotes elsewhere).
"""

from __future__ import annotations

import fnmatch
import importlib.util
import os
import re
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.messages import (
    ACTOR_HEADINGS,
    FAMILY_TOPICS,
    FRAMES,
    MESSAGES,
    TOPIC_TITLES,
    topic_of,
)
from pitloom.messages import _model_field as model_field
from pitloom.messages import _model_stub as model_stub

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "generate_message_reference.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_message_reference", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.platform  # paths, globs, line ends, a subprocess

gen = _load()
_DOCS = gen.SITES[0]
_BODY = gen.render(_DOCS)
_BLOCKS = [
    *((s.index, gen.BEGIN, lambda s=s: gen.render(s)) for s in gen.SITES),
    *((path, gen.MODEL_BEGIN, gen.render_model_table) for path in gen.MODEL_TARGETS),
]


@pytest.mark.parametrize(
    ("path", "begin", "render"),
    _BLOCKS,
    ids=[path.relative_to(_ROOT).as_posix() for path, _, _ in _BLOCKS],
)
def test_a_target_holds_what_the_script_renders(
    path: Path, begin: str, render: Callable[[], str]
) -> None:
    current = path.read_bytes()
    text = current.decode("utf-8")
    wanted = gen.replace_block(text, render(), begin).encode("utf-8")
    assert current == wanted, (
        f"{path.relative_to(_ROOT).as_posix()} is stale: run "
        "'python scripts/generate_message_reference.py' and commit it"
    )
    assert b"\r" not in current


def test_git_checks_every_target_and_page_out_with_lf() -> None:
    """A Windows checkout (``core.autocrlf``) writes CRLF, so the bytes
    differ from the render, unless ``.gitattributes`` pins the file to LF."""
    lines = (_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    patterns = [ln.split()[0] for ln in lines if ln.endswith(" text eol=lf")]
    pages = [s.path(t) for s in gen.SITES for t in TOPIC_TITLES]
    for path in (*gen.TARGETS, *pages, *gen.MODEL_TARGETS):
        name = path.relative_to(_ROOT).as_posix()
        assert any(_git_matches(name, pat) for pat in patterns), name


def _git_matches(name: str, pattern: str) -> bool:
    """*name* matches *pattern* as ``.gitattributes`` does: a ``*`` stays
    within one path segment (``fnmatch`` lets it cross ``/``)."""
    parts, wanted = name.split("/"), pattern.split("/")
    return len(parts) == len(wanted) and all(
        fnmatch.fnmatchcase(p, w) for p, w in zip(parts, wanted, strict=True)
    )


@pytest.mark.parametrize(
    ("name", "pattern", "expected"),
    [
        ("skills/x/references/messages.md", "skills/*/references/messages*.md", True),
        ("skills/x/references/messages.md", "skills/*/messages*.md", False),
        ("docs/message-codes-files.md", "docs/message-codes*.md", True),
        ("docs/a/message-codes.md", "docs/message-codes*.md", False),
    ],
    ids=["segment", "no-cross-slash", "docs", "nested"],
)
def test_the_git_match_does_not_let_a_star_cross_a_slash(
    name: str, pattern: str, expected: bool
) -> None:
    assert _git_matches(name, pattern) is expected


def test_the_docs_catalogue_has_its_own_index() -> None:
    """The guide links the index that lists the codes, and holds none itself."""
    guide = (_ROOT / "docs" / "messages.md").read_text(encoding="utf-8")
    assert gen.BEGIN not in guide and "(message-codes.md)" in guide
    assert _DOCS.index == _ROOT / "docs" / "message-codes.md"


def test_the_model_table_lists_every_cause_that_thins_a_model() -> None:
    """Each entry of the model-stub and model-field modules whose effect
    leaves the model thinner, and the cap and pointer families, in the order
    of their codes, each linked to its section beside the page."""
    entries = (*model_stub.ENTRIES, *model_field.ENTRIES)
    thinner = {m.code for m in entries if m.effect == "thinner"}
    wanted = thinner | {"over-cap", "lfs-pointer", "lfs-pointer-malformed"}
    assert set(gen.MODEL_OUTCOMES) == wanted
    assert all(MESSAGES[code].effect == "thinner" for code in gen.MODEL_OUTCOMES)
    rows = [r for r in gen.render_model_table().splitlines() if r.startswith("| [")]
    assert [r.split("`")[1] for r in rows] == sorted(wanted)
    for code in wanted:
        link = f"(messages-{topic_of(code)}.md#{gen.slug(code)})"
        assert link in gen.render_model_table()


def _sections() -> dict[str, list[str]]:
    """The lines of each code's section, by code, over the docs pages."""
    found: dict[str, list[str]] = {}
    for topic in TOPIC_TITLES:
        for line in gen.render_page(_DOCS, topic).splitlines():
            if line.startswith("### `"):
                found[line.split("`")[1]] = []
            elif found:
                found[next(reversed(found))].append(line)
    return found


def test_the_index_and_the_pages_list_every_code_in_order() -> None:
    for site in gen.SITES:
        rows = [r for r in gen.render(site).splitlines() if r.startswith("| [`")]
        assert [r.split("`")[1] for r in rows] == sorted(MESSAGES)
        assert {r.count(" | ") for r in rows} == {2}
        for code in MESSAGES:
            assert f"]({site.link(code)})" in gen.render(site)
        for topic in TOPIC_TITLES:
            page = gen.render_page(site, topic).splitlines()
            rows = [r for r in page if r.startswith("| [`")]
            codes = sorted(c for c in MESSAGES if topic_of(c) == topic)
            assert [r.split("`")[1] for r in rows] == codes
            assert {r.count(" | ") for r in rows} == {3}
    assert sorted(_sections()) == sorted(MESSAGES)
    assert gen.slug("lfs-pointer/shipped") == "lfs-pointershipped"


@pytest.mark.parametrize("code", sorted(MESSAGES), ids=str)
def test_a_section_says_what_its_code_means_and_every_line(code: str) -> None:
    message = MESSAGES[code]
    text = "\n".join(_sections()[code])
    for bullet in ("Level", "Means", "SBOM effect", "Pitloom did", "Lines"):
        assert f"- **{bullet}**: " in text or f"- **{bullet}**:\n" in text
    for actor, heading in ACTOR_HEADINGS.items():
        assert (f"- **{heading}**: " in text) is (message.actor == actor)
    assert (gen.ERROR_RULE.split()[0] in text) is ("ERROR" in message.levels)
    for line in message.lines:
        assert f"  {line.level}: {line.shown} [{code}]" in text.splitlines()


def test_the_prefixes_are_the_catalogues_frames() -> None:
    rows = [r for r in gen.render(_DOCS).splitlines() if "<text>` |" in r]
    assert len(rows) == len(FRAMES)
    for frame in FRAMES:
        head = f"| `{frame.shown}<text>` |"
        assert any(r.startswith(head) and frame.surface in r for r in rows), head


_RENDERS: list[tuple[str, Callable[[], str]]] = [
    ("index", lambda: _BODY),
    ("model", gen.render_model_table),
    *(
        (
            f"{site.index.parent.parent.name}-{topic}",
            lambda s=site, t=topic: gen.render_page(s, t),
        )
        for site in gen.SITES
        for topic in TOPIC_TITLES
    ),
]


@pytest.mark.parametrize(
    "render", [r for _, r in _RENDERS], ids=[name for name, _ in _RENDERS]
)
def test_the_output_lints_clean(render: Callable[[], str]) -> None:
    """Outside code blocks: no code span with a space at an edge; outside
    tables too, no line over 80 characters and none starting with ``<``
    (an HTML block)."""
    fenced = False
    for line in render().splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        if fenced:
            continue
        assert all(span == span.strip() for span in re.findall(r"`([^`]+)`", line))
        if line.startswith(("|", "<!--", "SPDX-", "---")):
            continue
        assert len(line) <= gen.WIDTH, line
        assert not line.lstrip().startswith(("<", "`<")), line


@pytest.mark.parametrize(
    ("text", "first", "rest"),
    [
        ("word " * 40, "- **Means**: ", "  "),
        ("a " + "x" * 72 + " <file> and " + "y" * 70 + " `<file>` and more", "", ""),
    ],
    ids=["fill", "angle"],
)
def test_wrap_fills_to_80_and_never_starts_a_line_with_an_angle(
    text: str, first: str, rest: str
) -> None:
    lines = gen.wrap(text, first, rest)
    assert len(lines) > 1 and lines[0].startswith(first)
    assert all(ln.startswith(rest) for ln in lines[1:])
    assert " ".join(" ".join(lines).split()) == " ".join(f"{first}{text}".split())
    for line in lines[1:]:
        assert not line[len(rest) :].startswith(("<", "`<")), line
    assert all(len(ln) <= gen.WIDTH for ln in lines)


def test_a_pipe_in_a_cell_is_escaped() -> None:
    assert gen.cell("a | b\n c") == "a \\| b c"


@pytest.mark.parametrize(
    "text",
    [
        "no markers",
        f"{gen.BEGIN}\n{gen.BEGIN}\n{gen.END}",
        f"{gen.END}\n{gen.BEGIN}",
        f"{gen.BEGIN}",
    ],
    ids=["none", "twice", "reversed", "unclosed"],
)
def test_markers_that_are_not_one_pair_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="GENERATED|before"):
        gen.replace_block(text, "x")


def test_only_the_block_is_rewritten() -> None:
    before = f"head\n{gen.BEGIN}\nold\n{gen.END}\ntail\n"
    after = gen.replace_block(before, "new")
    assert after == f"head\n{gen.BEGIN}\nnew\n{gen.END}\ntail\n"
    assert gen.replace_block(after, "new") == after


def test_check_fails_with_a_diff_on_a_stale_target_and_write_fixes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.md"
    target.write_bytes(f"a\n{gen.BEGIN}\nold\n{gen.END}\nb\n".encode())
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.run([target], check=True, body=_BODY) == 1
    err = capsys.readouterr().err
    assert "-old" in err and "+| Code |" in err and "stale" in err
    assert target.read_bytes().endswith(b"old\n" + gen.END.encode() + b"\nb\n")
    assert gen.run([target], check=False, body=_BODY) == 0
    assert gen.run([target], check=True, body=_BODY) == 0
    written = target.read_bytes()
    assert b"\r" not in written and b"\nold\n" not in written


def test_a_target_without_markers_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.md"
    target.write_bytes(b"nothing\n")
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.run([target], check=True, body=_BODY) == 2
    assert capsys.readouterr().err.startswith("ERROR: t.md: ")


def test_the_command_line_checks_the_tree() -> None:
    run = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--check"],
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src"), "PYTHONUTF8": "1"},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")


def test_every_family_has_one_topic_and_no_topic_is_empty() -> None:
    families = {code.partition("/")[0] for code in MESSAGES}
    assert families == set(FAMILY_TOPICS), "map each new family in _topics.py"
    assert set(FAMILY_TOPICS.values()) == set(TOPIC_TITLES)
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", t) for t in TOPIC_TITLES)


@pytest.mark.parametrize(
    ("code", "topic"),
    [("over-cap", "files"), ("reader-unsafe/remote", "models")],
    ids=["family", "variant"],
)
def test_a_variant_sits_on_its_familys_page(code: str, topic: str) -> None:
    assert topic_of(code) == topic == topic_of(code.partition("/")[0])


def test_an_unmapped_family_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        topic_of("no-such-family/variant")


def test_every_generated_file_fits_the_size_limit() -> None:
    for site in gen.SITES:
        for path in (site.index, *gen.expected_pages(site)):
            assert gen.too_big(path.name, path.read_bytes()) is None, path


@pytest.mark.parametrize(
    ("data", "refused"),
    [
        (b"x" * 30_000, False),
        (b"\n" * 800, False),
        (b"x" * 30_001, True),
        (b"\n" * 801, True),
    ],
    ids=["bytes-at-limit", "lines-at-limit", "bytes", "lines"],
)
def test_the_size_guard_refuses_just_over_the_limit(data: bytes, refused: bool) -> None:
    result = gen.too_big("f.md", data)
    assert (result is not None) is refused
    assert result is None or "_topics.py" in result


def test_a_page_with_no_topic_is_an_orphan(tmp_path: Path) -> None:
    site = gen.Site(
        index=tmp_path / "messages.md",
        page="messages-{}.md",
        title="{}",
        see_also="x.",
    )
    kept = site.path("models")
    kept.write_text("x", encoding="utf-8")
    stray = tmp_path / "messages-old-topic.md"
    stray.write_text("x", encoding="utf-8")
    (tmp_path / "messages.md").write_text("index", encoding="utf-8")
    assert gen.orphans(site) == sorted([stray])
    assert kept not in gen.orphans(site)


def test_pages_are_written_whole_then_stay_unchanged_and_an_orphan_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    site = gen.Site(
        index=tmp_path / "messages.md",
        page="messages-{}.md",
        title="T {}",
        see_also="See x.",
    )
    assert gen.run_pages(site, check=True) == 1  # nothing written yet
    assert "stale" in capsys.readouterr().err
    assert gen.run_pages(site, check=False) == 0
    first = {p: p.read_bytes() for p in gen.expected_pages(site)}
    assert len(first) == len(TOPIC_TITLES) and all(first.values())
    assert gen.run_pages(site, check=True) == 0
    stray = tmp_path / "messages-gone.md"
    stray.write_bytes(b"x")
    for check in (True, False):
        assert gen.run_pages(site, check=check) == 1
        assert "messages-gone.md: no topic produces it" in capsys.readouterr().err
    assert stray.read_bytes() == b"x"  # the script never deletes


def test_an_oversize_page_is_an_error_and_is_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "MAX_BYTES", 100)
    site = gen.Site(
        index=tmp_path / "messages.md",
        page="messages-{}.md",
        title="{}",
        see_also="x.",
    )
    assert gen.run_pages(site, check=False) == 1
    assert "over 100 bytes" in capsys.readouterr().err
    assert not list(tmp_path.glob("messages-*.md"))


def test_the_command_line_names_an_oversize_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    index = tmp_path / "i.md"
    index.write_bytes(f"{gen.BEGIN}\nold\n{gen.END}\n".encode())
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "MAX_LINES", 5)
    assert gen.run([index], check=False, body=gen.render(_DOCS)) == 1
    assert "i.md: " in capsys.readouterr().err and "old" in index.read_text("utf-8")


def test_the_pages_list_counts_a_single_code_in_the_singular() -> None:
    lines = gen.page_list(_DOCS)
    assert [ln for ln in lines if ln.endswith(": 1 code")] == [
        f"- [Licences]({_DOCS.path('licences').name}): 1 code"
    ]


def test_a_site_names_each_codes_page_and_anchor() -> None:
    """``Site.link`` and ``Site.path`` follow the topic, not the index (a
    page's anchor is the slug of its code)."""
    site = gen.SITES[1]
    assert site.path("files") == site.index.with_name("messages-files.md")
    assert gen.SITES[0].path("pypi").name == "message-codes-pypi.md"
    assert site.link("over-cap") == "messages-files.md#over-cap"
    assert site.link("reader-unsafe/remote") == "messages-models.md#reader-unsaferemote"


def test_an_unmapped_family_names_the_module_to_edit() -> None:
    with pytest.raises(KeyError, match=r"no-such.*_topics\.py"):
        topic_of("no-such/variant")


@pytest.mark.parametrize("kind", ["text", "mapping"])
def test_a_block_body_is_a_text_or_a_text_by_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    target = tmp_path / "t.md"
    target.write_bytes(f"a\n{gen.BEGIN}\nold\n{gen.END}\nb\n".encode())
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    body: object = "new" if kind == "text" else {target: "new"}
    assert gen.run([target], check=False, body=body) == 0
    assert target.read_bytes() == f"a\n{gen.BEGIN}\nnew\n{gen.END}\nb\n".encode()


def test_main_checks_the_tree_in_process(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen.main(["--check"]) == 0
    assert capsys.readouterr().err == ""
