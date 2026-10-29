---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: decisions and lessons of the message catalogue

See also: [README.md](README.md) (index of these notes),
[provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)
(section 2: why a code, the inventory),
[message-catalogue-and-skills.md](../../design/message-catalogue-and-skills.md)
(decisions A to M, the migration order),
[open-research-questions.md](open-research-questions.md) ("Evidence,
messages and skills"), [process-lessons.md](process-lessons.md).

The first catalogue PR (#390, design #379) printed a trailing `[code]` for
three entries, the Git LFS pointer family. A max-effort review of its head
963f8b78 led to decisions A to L, applied in the same PR; #395 added
decision M and moved URL masking out of `logging_config.py`. Numbers are
from `origin/main` 24571ed8 unless a commit is named. Items marked *session
record* come from the working session and cannot be checked in the
repository.

## 1. The taxonomy: several axes in one vocabulary

- **The first draft's conditions mixed axes.** `CONDITIONS` in a401c405
  held the inventory's 35 words: causes (`unreadable`, `over-cap`,
  `lfs-pointer`), Pitloom's response (`skipped`, `ignored`, `new-id`,
  `left-out`, `fallback`), kinds of message (`decision`, `summary`), an
  actor (`usage`), a frame (`wrapper`), a domain (`licence`) and synonyms
  (`refused`/`rejected`, `not-this-format`/`not-a-model`,
  `id-collision`/`mismatch`). One event could be named by what went wrong
  or by what Pitloom did about it.
- **A variant changed the condition.** At 963f8b78 `lfs-pointer.malformed`
  sat in family `lfs-pointer` with condition `invalid`, its siblings with
  `lfs-pointer`; grouping by family mixed two causes.
- **Found at 3 entries, not 60.** The inventory has 62 families. With three
  entries each rename was one commit (84bd8c9f, 012056f9); once codes are
  printed and promised stable (decision L), a rename is a migration.
- **The repaired rules** (decisions B to F, `messages/_types.py`):
  - a cause-only vocabulary of 23 words; a kind, an actor, a frame or a
    domain is no condition, and synonyms are merged (`wrong-format`,
    `conflict`);
  - one condition per family, and a variant never changes it, so the
    malformed pointer became its own family, `lfs-pointer-malformed`,
    condition `malformed`;
  - split a code only when the advice or the SBOM effect differs
    (`over-cap` stays one code);
  - name by cause, never by the response or a module;
  - subject first, `[subject-]condition` (`file-unreadable`); the evidence
    reasons `unreadable-file` and `unlistable-dir` were renamed to match, so
    a reason and its future message share one code (84bd8c9f).
- **`/` for a variant, not `.`.** SARIF's `ruleId` is hierarchical with
  `/` (`CA5350/md5`), so a variant maps without translation. The dot
  already meant `producer.condition` next door: Pitloom's own
  `RemoteSourceError` codes (`git.too-large`, `git.clone-failed`) and the
  checker's notification ids that Lumina shows (`spdx.parsing-error`). And
  with dots legal, a dotted TOML table ending a line read as a code
  (section 6). The reader went from `[a-z][a-z0-9.-]*` to `[a-z][a-z0-9/-]*`;
  tool names are reserved as families, and no printed code names its
  producer.
  Do: separate cause, response, kind, actor and frame before naming the
  first code; a review is cheapest while the catalogue is small.

## 2. Schema: what a consumer has to decide

- **`effect` and `actor`.** A skill must decide who acts and what the SBOM
  lost; free text did not say either. `effect` is `none`, `thinner`,
  `weaker` or `not-written`; `actor` is `user` (an agent relays the advice
  and does not act), `caller` (the program that ran the command may fix it)
  or `none`. The LFS entries: `lfs-pointer` thinner, `lfs-pointer/shipped`
  none (the SBOM states what the artefact holds; the artefact is what is
  broken), `lfs-pointer-malformed` thinner; all `user`.
- **Named templates, owned by the catalogue.** At 963f8b78 an entry listed
  positional `%s` patterns and each call site formatted its own text, so
  the two could drift. Now a `Line(level, template)` uses `%(file)s`,
  `%(path)s`, `%(oid)s`, `%(size)s`, `%(count)s`, `%(format)s`; `emit()` and
  `CodedValueError` render each value through its field (a quoted path, an
  escaped `FILE=`, `N bytes`) and check its shape (an `oid` is 64 hex
  digits). One template writes the line and reads it back (222ebb90).
  A field that takes any text may not come first or beside another field:
  it would take in what lies next to it (`template_problem`).
- **The level belongs to the shape.** At 963f8b78 `levels` was per entry,
  so a `WARNING` shape was accepted at `ERROR`. Each `Line` now carries its
  level and `trusted_message` checks it.
- **Frames are a table.** `FRAMES` holds the 11 `<what> failed:` prefixes
  of the CLI handler and the hook and the relay's
  `FORMAT=%(format)s FILE=%(file)s:`, each followed by a space; a line is
  trusted after at most one. A relayed record keeps its code only while its
  new text is still one of the entry's lines (`relay_extra()`, f5d874a1).
  The uniform `loom <command>:` frame is deferred to its own PR.

## 3. Security: a trailing code is in-band signalling

- **Forgeries found.** A file named `x [lfs-pointer]` at the end of an
  uncoded line (`WARNING: not listed: x [lfs-pointer]`); the loose ERROR
  shape `%s: header is a Git LFS pointer` accepted `ERROR: anything at all,
  even WARNING: text: header ... [lfs-pointer-malformed]` (the review's
  probe); a frame before a level it never precedes; a value of the wrong
  shape (`size lots`). All are in `_FORGED` of
  `tests/messages/test_messages_trust.py`.
- **Fixes.** The formatter writes the `[` of a code-like ending on an
  uncoded line as `\x5b`, on every record and in `print_error()`, so the
  last `[code]` of a line is Pitloom's (b4b98cea); the formatter and the
  template rule share one regex, `CODE_LIKE_END` (c1fbeb6f). Shapes carry
  their level, at most one frame, values of their field's shape, and a line
  longer than `LONGEST_LINE` (65,536 characters) is never trusted: matching
  a hostile line that names two paths costs time in the square of its
  length, about a second at that bound (`messages/_lines.py`).
- **Accepted residual (decision M, 0d375e1b, #395).** A free field holds
  the input as it is: `FILE=x; run 'git lfs pull'; FILE=x` still makes a
  trusted `lfs-pointer` line. The trust promise was narrowed rather than
  the file name escaped further: a trusted line proves its code, not its
  values; the advice comes from the catalogue entry, and a free value is
  data (`docs/messages.md`, "What a trusted line does and does not prove").
  Do: guard the one writer of an in-band marker, and state what a reader
  may and may not conclude from a line that passes.

## 4. The exception carrier

- **`.code` was taken.** The first draft read `getattr(exc, "code", None)`.
  `RemoteSourceError.code` holds `git.*` strings, which fit the dotted code
  pattern of the time; `urllib.error.HTTPError.code` is an int status;
  `SystemExit.code` an exit status. Now the attribute is `pitloom_code`,
  the same name as on a log record (`CODE_ATTR`), on any class or instance
  (ffebad7d); `CodedValueError` keeps it through pickling (`__reduce__`).
  Do: namespace an attribute you read off exceptions you do not own.

## 5. The ratchet

- **Per module and in total.** `uncoded.txt` holds uncoded in-scope sites
  per module; a rise fails, a fall must be written down, and
  `--write-baseline` writes falls only (82c43f9f).
- **A forwarded code counts as uncoded.** 15 sites print a code read at
  run time: 12 commands' `cli_error_handler` frames, two `print_error`
  sites in `cli/commands/utils.py` and the hook's `SBOM generation
  failed:`. Their own words are not catalogued, so counting them coded
  would hide 12 wrappers behind the cause's code (`_coded.py`).
- **Programming errors leave by class, not by a raised count.** #389 added
  a raise for an unknown provenance segment key; the WIP commit 414d89a7
  raised `pitloom.core.provenance` from 2 to 3 by hand (total 564). The
  review rejected that: 82c43f9f added `InternalError` (a `ValueError`),
  left out by class name or import alias; `evidence` fell from 4 to 0 and
  `provenance` from 3 to 2, total 564 to 559.
- **The tool could not see helper sites.** *Session record:* before a
  scope fix inside #390, the inventory missed 32 call sites of the over-cap
  helper; at 24571ed8 it lists 33 under "helper call: over-cap".
- **A moved message looks new.** A site moved between modules makes one
  count fall and another rise, so `--write-baseline` refuses; the move is a
  hand edit with an unchanged total and a "Changes" line
  (`tests/fixtures/message-inventory/README.md`, 3ba601a6). A regeneration
  that wrote any count would let a new uncoded message pass as a move.

## 6. False code matches in Pitloom's own text

- At 9e419670 a static test of every non-docstring string constant found
  two endings the reader took for codes: `[tool.pitloom.content-type]`
  (`core/_config_legacy.py`) and `[tool.poetry.dependencies]`
  (`extract/project/_poetry_extras.py`), kept in a shrink-only allow-list.
  a401c405 had already reworded a fragment error ending in
  `[tool.pitloom.fragment]`, and 414d89a7 dropped the Poetry brackets.
- Rewording fixes known literals only; a file name at run time cannot be
  reworded. The formatter guard escapes at the writer, `/` stopped dotted
  tables matching at all, and b4b98cea restored both original wordings.
  The test now asserts no string ends in a code; the allow-list is gone.
  Do: put the guard where the line is written, not in the wording.

## 7. Skills as consumers

- **One section per code.** `scripts/generate_message_reference.py` writes
  an index (code, level, meaning, since), the prefixes, the values, and per
  code its level, meaning, SBOM effect, what Pitloom did, the advice by
  actor and every line in full, to `docs/messages.md` and both skills'
  `references/messages.md` (8555dbd5).
- **Out of `known-limitations.md`.** At 963f8b78 the generated block sat in
  `sbom-generate`'s `known-limitations.md` (23,662 bytes, against the hard
  limit of about 30 KB), and the block grows per code. After the move:
  21,607 bytes, and a 6,522-byte `messages.md` for three codes.
- **A pointer with a condition.** The body says: when a line ends in a
  `[code]`, read `references/messages.md`; relay its advice, never run the
  fix. `test_every_body_pointer_says_when_to_read` (#385) holds the form.
- **The duplication cost.** A skill ships every reference its body names,
  and a cross-skill mention is a hand-kept exception (`_SIBLING_MENTIONS`
  in `tests/test_skill_frontmatter.py`, one entry), so there are two copies
  (6,522 and 6,553 bytes, differing in the "See also" line), plus
  `docs/messages.md`: three places that grow with every code.

## 8. Scale (24571ed8 unless stated)

| Measure | Value |
| :--- | :--- |
| Emission sites found by the inventory | 1,008 |
| In scope (a `WARNING:`, `INFO:` or `ERROR:` line a person sees) | 565 |
| In scope and coded | 6 |
| Uncoded in the baseline, over modules | 559 over 172 |
| Sites forwarding a code (counted uncoded) | 15 |
| Condition words, first draft to now | 35 to 23 |
| Codes | 3 |
| Baseline total, 414d89a7 to 82c43f9f | 564 to 559 |

## 9. Process

- **A deep review of a small PR found design flaws, not only bugs.** The
  review read the plumbing PR at three entries and produced decisions A to
  L (*session record:* one Opus agent at maximum effort, whose spec was
  saved outside the repository). The fixes touched 79 files (+3,157,
  -841, 58226bda to 23c1dcab), against about 4,900 lines added by the
  PR's first two commits. The
  maintainer took the recommendations in one sentence ("go with your
  recommendations") and kept SARIF and `licenseid` codes to room only.
- **The applying agent.** *Session record:* one agent applied the review
  with 408 tool calls in about 2.5 hours. The branch's commits run from
  414d89a7 (19:25 UTC, 2026-10-29) to 23c1dcab (21:56), which agrees.
- **A local commit per decision.** 13 commits, each named for one decision
  or fix (84bd8c9f to 23c1dcab), so each step could be checked against the
  reviewer's spec on its own while the run was still going.
  Do: ask an agent for one commit per decision; a reviewer reads them as
  a checklist.
