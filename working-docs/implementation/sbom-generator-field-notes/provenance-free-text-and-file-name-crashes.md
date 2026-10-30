---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: the second delimiter and the file name that crashed the writer

See also: [README.md](README.md) (index of these notes),
[provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)
(section 1: the `|` forgery and the two items it listed as "Still open",
which #402 closed),
[determinism-and-parsing.md](determinism-and-parsing.md) (a lone-surrogate
walk and its cost),
[id-registry-v3-lessons.md](id-registry-v3-lessons.md) (a registry name that
cannot be encoded),
[known-bugs.md](../../design/known-bugs.md) ("Found 2026-10-29").

Work of 2026-10-30: #402 (merged; commits 2a561bc0, 1abaf008, 64c7b944).
The earlier note records the grammar and the `|` forgery. This one adds
what PR 402 found and decided; it repeats none of that.

## 1. A file name that is not UTF-8 crashed every surface

- **The input.** A POSIX file name is bytes. `src/demo/\xff.py` is legal;
  Python reads it as `'\udcff.py'` (a lone surrogate, which no UTF-8 text
  can hold).
- **The crash was in the writer, not the reader.** The provenance
  Annotation passed (#389's sanitiser already writes a lone surrogate as
  the six characters `\udcff`). The crash was later, in
  `export/spdx3_json.py::_graph_sort_key`, which canonicalises the
  element's own `name` with RFC 8785 and raised there. Every surface that
  writes an SBOM hit it: `loom project`/`generate`, the library on a
  directory or an sdist, the Hatchling hook and a loom dataset; a model
  file was already escaped by its reader (known-bugs, 2026-10-29).
- **A sanitiser at the source does not protect a sink.** The sanitiser
  covered the strings it was called on. The element name was never one of
  them: it reaches the output as a file name, through code that builds an
  SPDX element. #386's per-site sanitising had the same shape: it left 13
  sites behind
  ([provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)).
- **The fix is at the one place every surface passes.** `to_json` decodes
  the serialiser's output and, before any pass reads a name, writes every
  lone surrogate in the graph as the text `\udcff`, with one `WARNING:`
  naming one element. The code names the smallest changed label
  (`min(changed)`), not the first met (the docstring says "first"), so the
  line does not depend on the order the graph was built in: the project's
  determinism rule, applied to stderr. The ID registry keys come from the
  on-disk spelling, not from this text (`escape_lone_surrogates_in_elements`;
  184 lines of surface tests in
  `tests/test_lone_surrogate_name_surfaces.py`).
  Do: when the output has one exit, put the last-resort guard there, and
  keep the per-reader escapes for the messages they give.
- **The wording had been copied five times.** The five readers that write a
  lone surrogate as text each logged the same `WARNING:` by hand. They now
  call one helper, `warn_lone_surrogates()`, "ready for the SBOM writer to
  use too" (2a561bc0). The writer is the sixth caller. The catalogue plan
  moves the helper into `pitloom.messages` as the code `text-malformed`
  (planned in the PR 2b plan; see
  [raw-exception-text-leaks-paths.md](raw-exception-text-leaks-paths.md)).
- **Lossy but unambiguous? Not checked.** `\udcff` in the SBOM stands for
  the byte `0xFF`. A file literally named with a backslash and `udcff` is
  a different file with the same output spelling. *Unverified*: whether
  two such names can reach one SBOM, and whether the writer should add a
  marker. (Open question below.)

## 2. A reader that accepts any `Key:` makes every string a key

- **The reader.** `parse_provenance_value` split each `|` segment on its
  first `:` and took the left side as a key, whatever it was. The writers
  put free text into segments too: the declared constraint (requirement
  text), the AUTHORS sentence, a version note. The requirement
  `pkg @ https://x/p.whl` therefore parsed as the key `pkg @ https`; a
  marker holding `:` did the same; so did the AUTHORS URL (key `fetched from
  authors at https`) and the note `version resolved` (known-bugs, #402).
- **Why it is the same bug as the `|` forgery.** The grammar has two
  delimiters, `|` between segments and `:` after a key. #389 made every
  writer sanitise the first. The second was left to the reader's
  tolerance, so free text that merely *contains* the delimiter was read as
  structure. A consumer that acts on keys (the merge drop on `Evidence:`,
  the fragment rule on `Method:`, `minimal` detail's keep-or-drop) could
  be steered by text, as before, if the invented key happened to match.
- **The fix has two halves.**
  1. The reader knows a closed set of keys: the segment keys, `Source`,
     `Evidence`, `Reason` and the numbered `Resolution-n`/`Expansion-n`.
     Any other segment, with a `:` or without, is a note, as is the value of
     a `Note:` segment. The notes are joined into one `note`.
  2. The writer `provenance_note()` puts free text that holds a `:` after
     the prefix `Note:`, so no part of it can reach the key position.
  Neither half alone is enough: a closed reader would still read free text
  that begins with a real key word (`Source: x`) as that key; the writer's
  `Note:` prefix stops that.
- **Rejected or not recorded.** Escaping every `:` in free text was not
  chosen; a URL holds colons legitimately, and the commit does not say why
  (*not recorded*). The lint that guards the builders
  (`tests/test_provenance_builders_lint.py`) was changed in the same commit.
- **The same shape, elsewhere in the project.** A `[code]` at the end of
  a stderr line is read by position, so a file named `x [lfs-pointer]`
  could forge it; the reader trusts a code only when the catalogue knows
  it and the text before it matches
  ([provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md),
  section 2). Both are in-band signalling where the reader accepts what the
  writer did not promise.
  Do: make the reader's vocabulary closed, whatever the writers promise.

## 3. What generalises

- Any SBOM generator that writes a human-readable string meant to be parsed
  back (a comment convention, a `key=value` note, a property value) has
  this surface. Pitloom writes one because SPDX 3 has no property for the
  evidence level of a value (FG-13 in
  [sbom-format-gaps.md](../../design/sbom-format-gaps.md)). The defence is
  the same in each case: one writer, a closed reader
  vocabulary, and a hostile-name test that runs the whole output.
- A crash on input the OS allows (a non-UTF-8 file name, a name with a
  newline or a colon) is a test-matrix row for every writer, not for the
  reader alone. Windows cannot create a file name with a colon, so those
  rows skip there (6e5bee77, #389).

## 4. Open

- Should an SBOM that holds a written-out lone surrogate say so
  (a marker in the name's own provenance), so that a consumer can tell
  `\udcff` the escape from `\udcff` the file name? The warning is on
  stderr only.
- Does any consumer of Pitloom's provenance other than Pitloom parse the
  string? None is known; the closed key set is now a contract that no
  consumer was asked about.
