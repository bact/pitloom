# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The parts of a message reference page: the text helpers (a table cell,
an anchor, a filled paragraph), the tables a page holds and the section of
each code.

See also: ``scripts/generate_message_reference.py`` (which puts the parts
together and writes the files) and ``scripts/message_reference/frames.py``
(the prefixes a section names).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from pitloom.messages import (
    ACTOR_HEADINGS,
    EFFECT_MEANINGS,
    FIELDS,
    FRAMES,
    MESSAGES,
    SUMMARIES,
    Line,
    Message,
)
from pitloom.messages._types import release_key
from scripts.message_reference.frames import frame_notes

WIDTH: Final = 80
LEVEL_ORDER: Final = ("ERROR", "WARNING", "INFO")
#: What an ``ERROR`` line means for any code (one code names the condition at
#: every level).
ERROR_RULE: Final = (
    "As an ERROR, the command stops for that input and writes nothing for it (exit 1)."
)
#: A code whose ERROR line ends the run another way.
ERROR_RULE_OVERRIDES: Final = {
    "interrupted": (
        "As an ERROR (Ctrl-C), the command stops and writes nothing (exit 130)."
    ),
    "registry-file-missing": (
        "As an ERROR (the library's IdRegistry.save() only), nothing is written;"
        " no command stops on it."
    ),
}


def cell(text: str) -> str:
    """*text* as one table cell: ``|`` escaped, a line break flattened."""
    return " ".join(text.split()).replace("|", "\\|")


def slug(heading: str) -> str:
    """The anchor a renderer gives *heading* (Python-Markdown's and
    GitHub's rule): lower case, punctuation but ``-`` dropped."""
    return re.sub(r"[^\w\s-]", "", heading).strip().lower().replace(" ", "-")


def wrap(text: str, first: str = "", rest: str = "") -> list[str]:
    """*text* filled to :data:`WIDTH` columns after *first* (then *rest*),
    never breaking a line before a word that starts with ``<`` or `` `< ``
    (such a line would start an HTML block)."""
    lines: list[list[str]] = [[]]
    width = WIDTH - len(first)
    for word in text.split():
        line = lines[-1]
        if line and len(" ".join([*line, word])) > width:
            moved = (
                [line.pop()] if word.startswith(("<", "`<")) and len(line) > 1 else []
            )
            lines.append([*moved, word])
            width = WIDTH - len(rest)
        else:
            line.append(word)
    return [(first if i == 0 else rest) + " ".join(ln) for i, ln in enumerate(lines)]


def levels(message: Message) -> str:
    """*message*'s levels, in :data:`LEVEL_ORDER`."""
    return ", ".join(lv for lv in LEVEL_ORDER if lv in message.levels)


def printed(message: Message, line: Line) -> str:
    """*line* of *message* as printed, each value shown as ``<name>``."""
    return f"{line.level}: {line.shown} [{message.code}]"


def codes_table(codes: Sequence[str]) -> list[str]:
    """A page's table of *codes*, each linked to its section of the page."""
    rows = [
        f"| [`{code}`](#{slug(code)}) | {levels(MESSAGES[code])} | "
        f"{cell(MESSAGES[code].summary)} | {MESSAGES[code].since} |"
        for code in codes
    ]
    return ["| Code | Level | Means | Since |", "| --- | --- | --- | --- |", *rows]


def frames_table() -> list[str]:
    """The index's table of the prefixes a line may start with."""
    rows = [
        f"| `{f.shown}<text>` | "
        f"{', '.join(lv for lv in LEVEL_ORDER if lv in f.levels)} | {f.surface} |"
        for f in FRAMES
    ]
    return ["| Prefix | Level | Printed by |", "| --- | --- | --- |", *rows]


def values_table() -> list[str]:
    """The values page's table: every name a line, a prefix or a summary
    uses, the lines' first."""
    used = sorted({n for m in MESSAGES.values() for ln in m.lines for n in ln.fields})
    framed = {n for f in FRAMES for n in f.fields}
    used += sorted((framed | {n for s in SUMMARIES for n in s.fields}) - set(used))
    rows = [f"| `{FIELDS[n].shown}` | {cell(FIELDS[n].meaning)} |" for n in used]
    return ["| Value | What it is |", "| --- | --- |", *rows]


def _advice(message: Message) -> list[str]:
    heading = ACTOR_HEADINGS[message.actor]
    text = message.advice
    if message.actor == "user":
        text = text.removeprefix("Tell the user ")
    return wrap(text, f"- **{heading}**: ", "  ")


def _spans(numbers: Sequence[int]) -> str:
    """*numbers* (ascending) with each run written ``first-last``."""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and runs[-1][-1] == number - 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return ", ".join(
        str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}" for run in runs
    )


def since_note(message: Message) -> str | None:
    """The code's release, then each later release and the lines (numbered
    as the section lists them) that first print in it; ``None`` when every
    line prints since the code's release."""
    later: dict[str, list[int]] = {}
    for number, line in enumerate(message.lines, start=1):
        since = line.effective_since(message)
        if since != message.since:
            later.setdefault(since, []).append(number)
    if not later:
        return None
    parts = [
        f"{'line' if len(found) == 1 else 'lines'} {_spans(found)}: {since}"
        for since, found in sorted(later.items(), key=lambda kv: release_key(kv[0]))
    ]
    return "; ".join([message.since, *parts])


def section(message: Message) -> list[str]:
    """*message*'s section of its topic page."""
    level = levels(message) + "."
    if "ERROR" in message.levels:
        level += f" {ERROR_RULE_OVERRIDES.get(message.code, ERROR_RULE)}"
    effect = f"{message.effect}: {EFFECT_MEANINGS[message.effect]}."
    since = since_note(message)
    return [
        f"### `{message.code}`",
        "",
        *wrap(level, "- **Level**: ", "  "),
        *wrap(message.summary, "- **Means**: ", "  "),
        *wrap(effect, "- **SBOM effect**: ", "  "),
        *wrap(message.did, "- **Pitloom did**: ", "  "),
        *_advice(message),
        *(
            ln
            for note in frame_notes(message, LEVEL_ORDER)
            for ln in wrap(note, "- **Printed after**: ", "  ")
        ),
        "- **Lines**:",
        "",
        "  ```text",
        *(f"  {printed(message, line)}" for line in message.lines),
        "  ```",
        *([] if since is None else ["", *wrap(since, "- **Since**: ", "  ")]),
    ]


#: What a page says of its summaries.
_SUMMARY_RULE: Final = (
    "A summary is an `INFO:` line that reports what a run did under its own "
    "rule (a count, the key it wrote), with no condition to name: it carries "
    "no code, and there is nothing to do."
)


def summaries(topic: str) -> list[list[str]]:
    """*topic*'s summaries section, or nothing when it has none."""
    found = sorted((s for s in SUMMARIES if s.topic == topic), key=lambda s: s.template)
    if not found:
        return []
    items: list[str] = []
    for summary in found:
        items += [
            *wrap(summary.meaning, "- ", "  "),
            "",
            "  ```text",
            f"  INFO: {summary.shown}",
            "  ```",
            "",
        ]
    return [["## Summaries"], wrap(_SUMMARY_RULE), items[:-1]]
