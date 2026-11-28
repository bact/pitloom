---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Rulings of 2026-11-28: the message catalogue as a second opinion

See also: [README.md](README.md) (the claim model),
[reason.md](reason.md) (ruling C2 in full), [basis.md](basis.md),
[conflict.md](conflict.md), [change.md](change.md),
[value-strength.md](value-strength.md), [source.md](source.md),
[renames-and-migration.md](renames-and-migration.md),
[findings-to-fix-first.md](findings-to-fix-first.md).

**Status:** rulings, written 2026-11-28. None is built, and the pages
they change are not yet rewritten: each row names the page to rewrite.

## Where they come from

The draft was read again against `main` dfa11c14 (release 0.25.1), and
the message catalogue (`src/pitloom/messages/`, released in 0.25.0)
was read as a second opinion on it. Two rules for that reading, from
the user on 2026-11-28:

- **The taxonomies come first.** They are concepts that hold longer
  and are exchanged with other parties, so they are harder to change;
  a message can be reworded to fit them.
- **The catalogue is heard.** It went through much work and many
  decisions, so where it draws a line the draft does not, that is a
  question to the draft; its wording has no veto.

Each question was put with the ways to settle it; the user ruled C1 to
C3 one by one and took the recommendations for C4 to C10.

## The rulings

| # | Question | Ruled | Page to rewrite |
| --- | --- | --- | --- |
| C1 | A source that Pitloom failed or refused to read loses fields of any kind (a card that does not parse, a reader not run); the draft records an outcome "for a content fact" only, so silence cannot tell "no source states it" from "the source was not read" | **The outcome of a source is recorded per source, on the element, for any field.** One record: the source, `failed` or `refused`, a reason. The fields stay silent. `not-measured` stays as it is for a content fact: the case where the source is the artefact itself and the field is known | [basis.md](basis.md#outcome-of-a-source); S1 of [value-strength.md](value-strength.md) |
| C2 | Whether a `Reason` is a catalogue code | **The taxonomy owns a small closed list; a catalogue code maps to it.** [reason.md](reason.md) | [basis.md](basis.md#reason-codes); rule 3 of [README.md](README.md) |
| C3 | Some selections are made by an order that says nothing of the values (the first reference, the first file found, "then by name"); `no-rule` is said to have no site today, and some sites record no loser | **A new rule `tie-break`:** the tool's fixed order chose, with no judgement of the values. `no-rule` stays, with its real sites. "A conflict is always recorded" binds both: a site that drops the loser is work for the code stage, not an exception | [conflict.md](conflict.md) (the rule list, its sites) |
| C4 | A split by a rule that can be wrong (an author read "by a guess") is `parsed`, defined as "nothing added" | **It stays `parsed`:** it is still the originator's statement. The doubt is shown by naming the technique and by a `Change` step, not by moving the value to `synthesized` | [method.md](method.md); [change.md](change.md) |
| C5 | A value written with escapes (`\uXXXX`, U+FFFD) differs from its source and has no `Change` kind; `cut` logs at `INFO:` | **A fifth kind, `escaped`:** the written form cannot hold the text as read. **`cut` logs at `WARNING:`** | [change.md](change.md) |
| C6 | A licence matcher that could not run (no database) against one that ran and found nothing | **Not the same.** No custom-text claim when the matcher did not run: a source outcome (C1) with a reason of the class "not able" | [asserter-licence.md](asserter-licence.md) |
| C7 | Pitloom's own stand-ins where a format requires a value (the name `unknown`, a creation time of 1970) | **A stand-in is no claim.** One small closed list, marked as such, as `placeholder-root` is today. A default source label (`Unknown source`) stays a fault to fix at the reader | [method.md](method.md); rule 5 of [basis.md](basis.md); [value-strength.md](value-strength.md) |
| C8 | A source that moves leaves no mark; a revision was asked for and the default branch read | **Rule C gains the row:** the revision asked for and the one read are both recorded. `Rule: default-branch` is written also when no commit is known. No time on a claim (the ruling on determinism stands) | [source.md](source.md) (rules C and D) |
| C9 | A clash that ends the run (a digest that differs from the one declared) against "a measured value stands over a declared one" | **The precedence governs recorded claims.** A check of integrity refuses before a claim exists, and is outside it | [basis.md](basis.md) (the precedence) |
| C10 | No rule says what may happen to a term once it is exchanged | **A released term is never renamed or reused.** A term that can no longer occur is marked retired and stays. From the first release that writes the new vocabulary | [README.md](README.md) (the rules); [renames-and-migration.md](renames-and-migration.md) |

## Open under these rulings

- C1: where the record sits (the fields Annotation, or one of its
  own), and whether one failed source gives one record or one per
  element it would have fed.
- C2: the cut of the reason list, whether the class is recorded, and
  `denied` ([reason.md](reason.md)).
- C3: which sites are `tie-break` and which become `no-rule`. A site
  that moves to `no-rule` loses a value that is written today, so it
  needs a sweep of output before and after.
- C4: the technique names, and whether the step is a new kind of
  `Change` or an existing one.
- C7: the members of the list.
- C9: whether the GGUF case (a key kept "as the file states it, not
  the length Pitloom would derive") is one fact with two candidates
  or a clash of names.

## Not checked

The questions rest on what the catalogue says each message does (its
"Pitloom did" text). That text is a claim. Read in the code at
dfa11c14 for these rulings: the texts quoted for C1 to C3, C5 (`cut`
and the four kinds) and C8 (`hub-revision-unpinned/url`). Not read in
the code: the author split of C4, each stand-in of C7, the GGUF case
of C9, and whether each site of C3 writes a conflict record. To read
before a page states them as facts.
