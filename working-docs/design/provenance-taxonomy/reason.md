---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Reason: why a source gave nothing

See also: [README.md](README.md) (the claim model),
[basis.md](basis.md) (the reason codes of today and the outcome of a
source), [resweep-rulings.md](resweep-rulings.md) (the other rulings of
the same day), [conflict.md](conflict.md),
[findings-to-fix-first.md](findings-to-fix-first.md).

**Status:** a ruling and its open questions, written 2026-11-28. Not
built; the list itself is not yet agreed.

## Ruled 2026-11-28: the reason list is the taxonomy's own

Ruled by the user on 2026-11-28, after the sweep against `main` dfa11c14
(release 0.25.1) and a reading of the message catalogue as a second
opinion on this draft. It replaces the first sentence of the section
"Reason codes" of [basis.md](basis.md#reason-codes) and its paragraph
on a gated repository; that section and its table are not yet
rewritten to it.

- **The taxonomy owns a small closed list of reasons.** It is cut by
  what a reader of the SBOM has to tell apart, not by what a user at
  the terminal has to do.
- **A catalogue code maps to a reason; it is no longer the same
  string by rule.** One table gives the reason of each catalogue code
  that can stand behind a recorded outcome, and a test holds the two
  together (as `tests/messages/test_drift_sources.py` holds
  `REASON_CODES` today). Where a catalogue family already names the
  cause (`over-cap`, `lfs-pointer`), the reason may keep that spelling.
- **A variant never enters the SBOM.** A catalogue code may gain a
  variant (`family/variant`) for finer advice; a reason has none.
- **The direction of fit.** The taxonomies are the lasting concepts
  that are exchanged with other parties; a message can be reworded to
  fit them. So a reason is not left out because the catalogue has no
  message for it: the `access-denied` case of that section is open again.

Why: the catalogue splits a code "only when the advice or the SBOM
effect differs", which is a rule for stderr, and its own note on
`over-cap` already says "a reason is SBOM data and a code a stderr
token, which may gain variants a reason must not"
(`src/pitloom/messages/_over_cap.py`, read at dfa11c14). One catalogue
family also holds two causes today: `file-unreadable/outside-project`
is a refusal by policy ("Pitloom reads no file outside it"), filed
under a family that section defines as "a permission or I/O error".

**Agreed with it, the same day: the catalogue may follow.** A later
revision of the catalogue can make its families the same as the
reasons of the taxonomy, so that the mapping is one to one at the level
of the family, with the variants below it for advice. The mapping is
the bridge until then, and the catalogue moves towards the taxonomy,
not the other way. It is work after the code stage, not a condition
of it. First candidates: a family of its own for a refusal by policy
(out of `file-unreadable`), and one for access denied.

Also to restate: rule 3 of [README.md](README.md) ("A `Reason` code is
a message catalogue code") and rule 8 of
`working-docs/design/evidence-levels.md` ("The same code in both
places").

**Not ruled.** Asked on 2026-11-28, no answer yet:

- The cut of the list. Put forward, not agreed: six classes by what
  the reader must tell apart.

  | Class | Meaning | Reasons and codes of today that fall in it |
  | --- | --- | --- |
  | fault | the read was tried and broke | `file-unreadable`, `dir-unlistable`, `download-network-failed`, a malformed source |
  | limit | a cap or a time bound stopped it | `over-cap`, `download-timeout` |
  | gate | Pitloom's safety policy did not allow the read; an option could | a reader not run, a file outside the project, a configuration not trusted |
  | denied | the other side refused access | HTTP 401 and 403; a private repository where it can be told |
  | stand-in | what was read is a pointer, not the content | `lfs-pointer` |
  | not able | the means to read is missing | a library or the licence database is missing |

- Whether the class itself is recorded (a key of its own, or the
  `Outcome`), with the reason under it, or the reason alone.
- Whether `denied` is kept for the cases that can be told (401, 403),
  given that the Hub answers 404 for a private repository.

The list has to serve more than content facts: by another ruling of
the same day the outcome of a source is recorded for any field, per
source ([basis.md](basis.md#outcome-of-a-source); not yet written
there).
