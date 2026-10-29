# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Find the messages the agent skills quote (``skills/**/*.md``) and match
each quote to the emission sites whose template it fits.

See also: ``__main__.py`` (``--quotes``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ._families import PH_RE

QUOTE_RE = re.compile(r"`([^`\n]*(?:WARNING:|ERROR:|INFO:)[^`\n]*)`")
LEVEL_WORD = re.compile(r"(WARNING|ERROR|INFO):")
#: Fewest literal characters a template needs to be matched at all.
MIN_LITERAL = 8
#: Share of a quote's words an approximate match must find in a template.
APPROX_SCORE = 0.8


def collect_skill_quotes(root: Path) -> list[dict[str, Any]]:
    """Every backtick-quoted (or fenced) tagged line under ``root/skills``."""
    out: list[dict[str, Any]] = []
    for path in sorted((root / "skills").rglob("*.md")):
        in_fence = False
        text = path.read_text(encoding="utf-8")
        for no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            hits = QUOTE_RE.findall(line)
            if in_fence and LEVEL_WORD.search(line):
                hits.append(stripped)
            for hit in hits:
                out.append(
                    {
                        "file": path.relative_to(root).as_posix(),
                        "line": no,
                        "text": hit,
                        "in_fence": in_fence,
                    }
                )
    return out


def template_regex(template: str) -> re.Pattern[str]:
    """A pattern matching *template* with each placeholder as ``.*?``."""
    parts: list[str] = []
    pos = 0
    for match in PH_RE.finditer(template):
        parts.append(re.escape(template[pos : match.start()]))
        parts.append(".*?")
        pos = match.end()
    parts.append(re.escape(template[pos:]))
    return re.compile("".join(parts), re.S)


def literal_len(template: str) -> int:
    """Characters of *template* outside its placeholders."""
    return len(PH_RE.sub("", template).strip())


def words(text: str) -> list[str]:
    """The words of *text* with four or more letters."""
    return re.findall(r"[A-Za-z][A-Za-z-]{3,}", text)


def _patterns(
    recs: list[dict[str, Any]],
) -> list[tuple[re.Pattern[str], dict[str, Any], str]]:
    pats = []
    for rec in recs:
        main = rec.get("template_after_tag") or rec["template"]
        for tmpl in [main] + list(rec.get("alt_templates") or []):
            if tmpl and literal_len(tmpl) >= MIN_LITERAL:
                pats.append((template_regex(tmpl), rec, tmpl))
    return pats


def _exact_hits(
    rest: str,
    frags: list[str],
    pats: list[tuple[re.Pattern[str], dict[str, Any], str]],
) -> set[str]:
    hits: set[str] = set()
    for pat, rec, tmpl in pats:
        tmpl_lit = PH_RE.sub("\x00", tmpl)
        if pat.search(rest) or (
            frags and all(f in tmpl_lit or pat.search(f) for f in frags)
        ):
            hits.add(f"{rec['file']}:{rec['line']}")
    return hits


def _best_overlap(
    qwords: list[str], pats: list[tuple[re.Pattern[str], dict[str, Any], str]]
) -> tuple[float, str]:
    best: tuple[float, str] = (0.0, "")
    for _pat, rec, tmpl in pats:
        twords = {w.lower() for w in words(PH_RE.sub(" ", tmpl))}
        score = sum(1 for w in qwords if w.lower() in twords) / len(qwords)
        if score > best[0]:
            best = (score, f"{rec['file']}:{rec['line']}")
    return best


def match_quotes(quotes: list[dict[str, Any]], recs: list[dict[str, Any]]) -> None:
    """Set ``matched``, ``n_matched`` and ``match_kind`` (``exact`` or
    ``approx``) on each quote, in place."""
    pats = _patterns(recs)
    for quote in quotes:
        found = LEVEL_WORD.search(quote["text"])
        quote["level"] = found.group(1) if found else None
        rest = quote["text"][found.end() :].strip() if found else quote["text"]
        rest = re.sub(r"<[^<>]+>|\.\.\.|\u2026", "\x00", rest)
        frags = [x.strip() for x in rest.split("\x00") if len(x.strip()) >= 6]
        hits = _exact_hits(rest, frags, pats)
        quote["matched"] = sorted(hits)[:5]
        quote["n_matched"] = len(hits)
        quote["match_kind"] = "exact" if hits else None
        qwords = words(" ".join(frags))
        if not hits and len(qwords) >= 2:
            score, where = _best_overlap(qwords, pats)
            if score >= APPROX_SCORE:
                quote["matched"] = [where]
                quote["n_matched"] = 1
                quote["match_kind"] = "approx"
            quote["best_score"] = round(score, 2)
