# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generate the message reference from :mod:`pitloom.messages`.

The catalogue is the source of truth. The reference is split into one page
per topic (:mod:`pitloom.messages._topics`), so no file nears the size limit.
For each site (the docs, and each skill's ``references/``) this script:

* rewrites only the text between ``<!-- BEGIN GENERATED: pitloom.messages
  -->`` and ``<!-- END GENERATED -->`` in the index (``message-codes.md``,
  ``messages.md``): a table of the codes, each linked to its page, the
  prefixes a line may start with and the pages;
* writes each topic page whole (``message-codes-<topic>.md``,
  ``messages-<topic>.md``): a table of its codes, then one section per code,
  sorted by code, naming each prefix a surface may print before its
  warnings and notes (``scripts/message_reference/frames.py``);
* writes the values page whole (``message-codes-values.md``,
  ``messages-values.md``): what each ``<name>`` a line shows stands for. It
  is a page of its own because the table grows faster than the code table
  and would take the index past :data:`MAX_BYTES`; no topic may be named
  ``values``.

In a skill's model-stub page it rewrites the block that opens ``<!-- BEGIN
GENERATED: pitloom.messages model-stub -->``: what each code leaves of a model
in the SBOM. The output has LF line endings, no dates and no line over 80
characters outside a table or a code block, and never starts a line with
``<``, so it is byte-for-byte reproducible and lints clean. A generated page
with no topic is an orphan, and a file over :data:`MAX_BYTES` or
:data:`MAX_LINES` is refused: split a topic in ``_topics.py`` (the script never
deletes a file).

    python scripts/generate_message_reference.py            # update (--write)
    python scripts/generate_message_reference.py --check   # exit 1 if stale
    python scripts/generate_message_reference.py --snapshot 0.25.0

``--snapshot RELEASE``, at a release bump, writes every line the catalogue
prints to ``tests/fixtures/message-catalogue/released-lines.tsv``
(``scripts/message_reference/snapshot.py``) and nothing else; a line
dated after *RELEASE* exits 1 unwritten.

``--check`` prints a unified diff of each stale target to stderr and exits 1;
an orphan page or an oversize file exits 1 as well. Exit status 2: a target
lacks the markers (or has them twice).

See also: ``scripts/message_reference/sections.py`` (a page's tables and
sections) and ``scripts/message_reference/snapshot.py`` (``--snapshot``).
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pitloom.messages import MESSAGES, TOPIC_TITLES, topic_of

ROOT: Final = Path(__file__).resolve().parents[1]
# The helper is found from the script, from ``python -m`` and from a loader
# that runs this file by its path.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# pylint: disable-next=wrong-import-position
from scripts.message_reference.sections import (  # noqa: E402
    cell,
    codes_table,
    frames_table,
    levels,
    section,
    slug,
    summaries,
    values_table,
    wrap,
)

# pylint: disable-next=wrong-import-position
from scripts.message_reference.snapshot import SNAPSHOT, write  # noqa: E402

#: The values page's slug, in a page's file name; not a topic.
VALUES_TOPIC: Final = "values"


@dataclass(frozen=True, kw_only=True)
class Site:
    """A place that holds the reference: an index and one page per topic.

    Attributes:
        index: The index file; it keeps a hand-written head and holds the
            generated block.
        page: A topic page's file name, ``{}`` standing for the topic slug.
        title: A page's heading, ``{}`` standing for the topic's title.
        see_also: The "See also" text of a page (wrapped by the script).
    """

    index: Path
    page: str
    title: str
    see_also: str

    def path(self, topic: str) -> Path:
        """The file of *topic*'s page."""
        return self.index.with_name(self.page.format(topic))

    @property
    def values_path(self) -> Path:
        """The file of the values page (a topic may not be named ``values``)."""
        return self.path(VALUES_TOPIC)

    def link(self, code: str) -> str:
        """A link target to *code*'s section: its page and its anchor."""
        return f"{self.path(topic_of(code)).name}#{slug(code)}"


_SKILL_SEE_ALSO: Final = (
    "`messages.md` (the index of every code), `../SKILL.md` (which holds the "
    "rule: explain and relay, never run the fix)."
)
#: Where the reference lives, the docs first.
SITES: Final = (
    Site(
        index=ROOT / "docs" / "message-codes.md",
        page="message-codes-{}.md",
        title="Message codes: {}",
        see_also=(
            "[Message codes](message-codes.md) (the index of every code) and "
            "[Messages and codes](messages.md) (the line grammar, what a code "
            "guarantees and when to trust one)."
        ),
    ),
    *(
        Site(
            index=ROOT / "skills" / skill / "references" / "messages.md",
            page="messages-{}.md",
            title="Pitloom's catalogued messages: {}",
            see_also=_SKILL_SEE_ALSO,
        )
        for skill in ("sbom-enrich", "sbom-generate")
    ),
)
#: The index files, which hold the generated block.
TARGETS: Final = tuple(site.index for site in SITES)
#: The files holding the model table, beside a skill's ``messages.md``.
MODEL_TARGETS: Final = (
    ROOT / "skills" / "sbom-enrich" / "references" / "model-stub-diagnosis.md",
)

BEGIN: Final = "<!-- BEGIN GENERATED: pitloom.messages -->"
#: Where the model table starts.
MODEL_BEGIN: Final = "<!-- BEGIN GENERATED: pitloom.messages model-stub -->"
END: Final = "<!-- END GENERATED -->"

#: What each code leaves of a model in the SBOM, for the model table: every
#: code whose cause leaves a model's SBOM entry thinner than its file.
MODEL_OUTCOMES: Final = {
    "library-missing": "a stub",
    "library-unusable": "a stub",
    "lfs-pointer": "no `ai_AIPackage`",
    "lfs-pointer-malformed": "no `ai_AIPackage`",
    "model-field-invalid": "read, without the release time",
    "model-field-unreadable": "read, without the fields the line names",
    "model-unreadable": "a stub",
    "model-wrong-format": "no `ai_AIPackage`",
    "over-cap": "a stub, or read with the cut the line names",
    "parameter-count-invalid": "read, with no parameter count",
    "reader-unsafe": "a stub (a wheel's gated formats)",
    "reader-unsafe/remote": "a stub (a Git URL's or a PyPI wheel's gated formats)",
}
#: A generated file may not pass these (CLAUDE.md: ~30 KB, 800 lines).
MAX_BYTES: Final = 30_000
MAX_LINES: Final = 800

_NOTE: Final = (
    "<!-- Generated by scripts/generate_message_reference.py; do not edit. -->"
)
_INTRO: Final = (
    "A catalogued line reads `LEVEL: text [code]`. Trust the code only when "
    "the text is one of the code's lines on its page (the table links it), a "
    "value in place of each `<name>` (the values page says what each is), "
    "after at most one prefix from the table of prefixes."
)


def _index(site: Site) -> list[str]:
    """The index's table: each code linked to its page. The summary is on the
    page, so the index stays small as the catalogue grows."""
    rows = [
        f"| [`{code}`]({site.link(code)}) | {levels(m)} | {m.since} |"
        for code, m in sorted(MESSAGES.items())
    ]
    return ["| Code | Level | Since |", "| --- | --- | --- |", *rows]


def page_list(site: Site) -> list[str]:
    """The list of the pages and how many codes each holds."""
    lines: list[str] = []
    for topic, title in TOPIC_TITLES.items():
        count = len(_topic_codes(topic))
        noun = "code" if count == 1 else "codes"
        lines.append(f"- [{title}]({site.path(topic).name}): {count} {noun}")
    lines.append(
        f"- [Values]({site.values_path.name}): what each `<name>` in a line is"
    )
    return lines


def _topic_codes(topic: str) -> list[str]:
    """The codes that *topic*'s page holds, sorted."""
    return sorted(code for code in MESSAGES if topic_of(code) == topic)


def render(site: Site) -> str:
    """The index's generated block, for *site*: LF, no trailing newline."""
    parts = [
        [_NOTE, *wrap(_INTRO)],
        page_list(site),
        _index(site),
        [
            *wrap("A line may start with one prefix before its text:"),
            "",
            *frames_table(),
        ],
    ]
    return "\n\n".join("\n".join(part) for part in parts)


def _page_rule(site: Site) -> str:
    """A page's reminder of the rule the index states (the prefixes are there;
    the values are on the values page of *site*)."""
    return (
        "Trust a code only when the line is one of the lines below, a value in "
        "place of each `<name>`, after at most one prefix: the index lists the "
        f"prefixes and `{site.values_path.name}` the values."
    )


_FRONT: Final = (
    "---\n"
    "SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul\n"
    "SPDX-FileType: DOCUMENTATION\n"
    "SPDX-License-Identifier: CC0-1.0\n"
    "---\n"
)


def render_page(site: Site, topic: str) -> str:
    """The whole file of *topic*'s page for *site*: LF, ending in one
    newline. It has no ``Created`` or ``Last-Modified`` date, so the output
    stays reproducible."""
    codes = _topic_codes(topic)
    parts = [
        [_FRONT.rstrip("\n")],
        [f"# {site.title.format(TOPIC_TITLES[topic])}"],
        wrap(site.see_also, "See also: ", ""),
        [_NOTE],
        wrap(_page_rule(site)),
        ["## Codes"],
        codes_table(codes),
        *(section(MESSAGES[code]) for code in codes),
        *summaries(topic),
    ]
    return "\n\n".join("\n".join(part) for part in parts) + "\n"


#: What the values page says of its table.
_VALUES_RULE: Final = (
    "A line shows each value as `<name>` in the catalogue; a line printed by "
    "Pitloom holds the value there. The table lists every name a line or a "
    "prefix uses."
)


def render_values_page(site: Site) -> str:
    """The whole file of the values page for *site*: LF, ending in one
    newline, with no date, like :func:`render_page`."""
    parts = [
        [_FRONT.rstrip("\n")],
        [f"# {site.title.format('Values')}"],
        wrap(site.see_also, "See also: ", ""),
        [_NOTE],
        wrap(_VALUES_RULE),
        ["## Values"],
        values_table(),
    ]
    return "\n\n".join("\n".join(part) for part in parts) + "\n"


def render_model_table(site: Site = SITES[1]) -> str:
    """The model table's body: each code of :data:`MODEL_OUTCOMES`, linked to
    its section of the page of *site* (a skill's) beside it, what it leaves of
    the model and what it means. LF, ending in a blank line (a table is
    followed by one)."""
    rows = [
        f"| [`{code}`]({site.link(code)}) | {cell(MODEL_OUTCOMES[code])} | "
        f"{cell(MESSAGES[code].summary)} |"
        for code in sorted(MODEL_OUTCOMES)
    ]
    head = ["| Code | The model | Means |", "| --- | --- | --- |"]
    return "\n".join([_NOTE, "", *head, *rows, ""])


def replace_block(text: str, body: str, begin: str = BEGIN) -> str:
    """*text* with what lies between *begin* and :data:`END` replaced by
    *body*.

    Raises:
        ValueError: The markers are missing, repeated or out of order.
    """
    if text.count(begin) != 1 or text.count(END) != 1:
        raise ValueError(f"needs exactly one {begin!r} and one {END!r}")
    head, _, rest = text.partition(begin)
    _, found, tail = rest.partition(END)
    if not found or END in head:
        raise ValueError(f"{END!r} comes before {begin!r}")
    return f"{head}{begin}\n{body}\n{END}{tail}"


def _updated(path: Path, body: str, begin: str) -> tuple[bytes, bytes]:
    """The bytes of *path* now, and as they should be."""
    current = path.read_bytes()
    wanted = replace_block(current.decode("utf-8"), body, begin).encode("utf-8")
    return current, wanted


def _diff(path: Path, current: bytes, wanted: bytes) -> str:
    """A unified diff from *current* to *wanted*, for *path*."""
    name = path.relative_to(ROOT).as_posix()
    return "".join(
        difflib.unified_diff(
            current.decode("utf-8").splitlines(keepends=True),
            wanted.decode("utf-8").splitlines(keepends=True),
            f"a/{name}",
            f"b/{name}",
        )
    )


def too_big(name: str, data: bytes) -> str | None:
    """Why *data*, the file *name*, is over the size limits, or ``None``."""
    lines = data.count(b"\n")
    if len(data) > MAX_BYTES or lines > MAX_LINES:
        return (
            f"{name}: {len(data)} bytes, {lines} lines; over {MAX_BYTES} bytes "
            f"or {MAX_LINES} lines; split a topic in pitloom/messages/_topics.py"
        )
    return None


def _report_stale(path: Path, current: bytes, wanted: bytes) -> None:
    name = path.relative_to(ROOT).as_posix()
    print(_diff(path, current, wanted), end="", file=sys.stderr)
    print(
        f"ERROR: {name}: stale; run 'python scripts/generate_message_reference.py'",
        file=sys.stderr,
    )


def run(
    targets: Sequence[Path],
    *,
    check: bool,
    begin: str = BEGIN,
    body: str | Mapping[Path, str] | None = None,
) -> int:
    """Update (or with *check*, only compare) the block opening *begin* in
    *targets* to *body*: a text for every target, or a text by target (the
    default: each index's :func:`render`). The exit status: 0, 1 (stale or
    oversize), 2 (a target without its markers)."""
    status = 0
    for path in targets:
        name = path.relative_to(ROOT).as_posix()
        text = _body_of(path, body)
        try:
            current, wanted = _updated(path, text, begin)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"ERROR: {name}: {exc}", file=sys.stderr)
            return 2
        big = too_big(name, wanted)
        if big:
            print(f"ERROR: {big}", file=sys.stderr)
            status = 1
        elif current == wanted:
            continue
        elif check:
            _report_stale(path, current, wanted)
            status = 1
        else:
            path.write_bytes(wanted)
            print(f"INFO: {name}: updated", file=sys.stderr)
    return status


def _body_of(path: Path, body: str | Mapping[Path, str] | None) -> str:
    """The block text for *path*."""
    if isinstance(body, str):
        return body
    if body is not None:
        return body[path]
    return render(next(site for site in SITES if site.index == path))


def expected_pages(site: Site) -> dict[Path, str]:
    """Every page of *site* (the topics' and the values page) and what it
    should hold."""
    pages = {site.path(topic): render_page(site, topic) for topic in TOPIC_TITLES}
    pages[site.values_path] = render_values_page(site)
    return pages


def orphans(site: Site) -> list[Path]:
    """The files that look like a page of *site* but that neither a topic nor
    the values page produces."""
    wanted = set(expected_pages(site))
    found = site.index.parent.glob(site.page.format("*"))
    return sorted(path for path in found if path not in wanted)


def run_pages(site: Site, *, check: bool) -> int:
    """Update (or with *check*, only compare) the pages of *site*; the exit
    status: 0, or 1 for a stale or oversize page or an orphan."""
    status = 0
    for path, text in expected_pages(site).items():
        name = path.relative_to(ROOT).as_posix()
        wanted = text.encode("utf-8")
        big = too_big(name, wanted)
        current = path.read_bytes() if path.is_file() else b""
        if big:
            print(f"ERROR: {big}", file=sys.stderr)
            status = 1
        elif current == wanted:
            continue
        elif check:
            _report_stale(path, current, wanted)
            status = 1
        else:
            path.write_bytes(wanted)
            print(f"INFO: {name}: updated", file=sys.stderr)
    for path in orphans(site):
        name = path.relative_to(ROOT).as_posix()
        print(f"ERROR: {name}: no topic produces it; remove it", file=sys.stderr)
        status = 1
    return status


def main(argv: Sequence[str] | None = None) -> int:
    """The command line."""
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n", maxsplit=1)[0]
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="exit 1 with a diff if a target is stale"
    )
    mode.add_argument(
        "--write", action="store_true", help="update the targets (the default)"
    )
    mode.add_argument(
        "--snapshot",
        metavar="RELEASE",
        help="at a release bump: write the lines RELEASE prints to "
        f"{SNAPSHOT.as_posix()}, and nothing else",
    )
    args = parser.parse_args(argv)
    if args.snapshot is not None:
        return write(ROOT, args.snapshot)
    status = run(TARGETS, check=args.check)
    if status == 2:
        return status
    for site in SITES:
        status = max(status, run_pages(site, check=args.check))
    model = run(
        MODEL_TARGETS, check=args.check, begin=MODEL_BEGIN, body=render_model_table()
    )
    return max(status, model)


if __name__ == "__main__":
    sys.exit(main())
