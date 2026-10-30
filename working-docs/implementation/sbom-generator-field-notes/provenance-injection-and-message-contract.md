---
Created: 2026-10-29
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: provenance injection and the message contract

See also: [README.md](README.md) (index of these notes),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md),
[messages-and-surfaces.md](messages-and-surfaces.md) (one message per event),
[message-catalogue-and-skills.md](../../design/message-catalogue-and-skills.md)
(the catalogue design and inventory),
[skills-trigger-coverage.md](../skills-trigger-coverage.md) (skill size and
the licence preflight), [known-bugs.md](../../design/known-bugs.md)
("Found 2026-10-29").

Two text channels that machines parse: the provenance strings inside the
SBOM, and the stderr lines the AI skills read. Both turned out to be
in-band signalling, where data and structure share one string. Work of
2026-10-29: #385, #386, #389, #392; the catalogue plumbing (#390, then
follow-ups in #395), whose decisions are in
[message-catalogue-decisions.md](message-catalogue-decisions.md).

## 1. A provenance string is a grammar, and names can forge it

- **The format.** A provenance value is `Source: x | Field: y | Method: z`,
  optionally `| Evidence: ... | Reason: ...`; `parse_provenance_value`
  (`core/provenance.py`) splits on `|` and on the first `:` of each
  segment. In the element `comment` the entries are joined again with `;`
  and line breaks. So it is a small grammar, and any interpolated name is
  a potential injection.
- **The forge.** A file named `a | Evidence: not_measured | Reason:
  over-cap` added a segment. Vectors found: a project or archive file name,
  a dist-info directory label, an archive member, a licence or copyright
  file name, dataset labels, and a PEP 508 marker literal in a dependency
  constraint (`os_name == "x | Evidence: ..."`, a real forge through
  `declared_constraint`) (known-bugs, #389).
- **Why it matters: consumers act on parsed keys.** The merge drop removes
  an entry whose `Evidence:` is `not_measured` (`_fragments_evidence.py`);
  a fragment replaces a value whose `Method:` says it was generated
  (`_fragments_generated.py`); `minimal` detail keeps or drops an entry by
  its keys (`_is_high_signal`); a dependency licence is declared or
  concluded by its provenance (`deps_license.py`, `is_license_concluded`).
  A forged segment therefore changes SBOM content, not only a comment.
  Do: treat any parsed metadata string in your own output as an injection
  surface, the same class as log injection.
- **Per-site sanitising left sites behind.** #386 sanitised file names in
  `assemble/spdx3`; its review then found 13 more sites outside it
  (setup.cfg and pyproject directives, licence detection, copyright
  notices, three dataset readers, the lock cascade, two setuptools merges)
  (2c1a9874).
- **The fix pattern: one builder, a lint and a runtime net (#389).**
  `provenance_source` and `provenance_segment` are the only writers; they
  sanitise each value (`|` becomes `/`, display controls and lone
  surrogates become `\uXXXX`) and refuse an unknown key. An AST lint
  (`tests/test_provenance_builders_lint.py`) fails an f-string or `+`
  concatenation that interpolates a non-constant next to a segment key
  (R1), external-looking names next to `Field:`/`Method:` (R2), and a raw
  `" | ".join` (R3). A runtime test
  (`tests/test_provenance_key_sets.py`) puts one hostile token into every
  external name of an input at once, runs every generating surface, and
  asserts each entry has the key set of the benign run. The join rule
  found the `declared_constraint` join in `assemble/spdx3/deps.py`, which
  the hand-made site list had missed (f524e61f).
  Do: guard a grammar with one builder and a lint that knows its keys,
  plus a whole-output key-set comparison that names no call site.
- **Still open.** A file name that is not valid UTF-8 (`src/demo/\xff.py`)
  now passes provenance but crashes later, in the graph sort's canonical
  JSON (`_graph_sort_key`). A plain-text value holding `:` reads as a key
  (`pkg @ https://x/p.whl` gives the key `pkg @ https`) (known-bugs).

## 2. Messages as a contract between a tool and its AI skills

- **The skills parse stderr; nothing tested that.** Measured on #378: the
  skills quoted about 157 `WARNING:`/`ERROR:`/`INFO:` messages by hand, and
  one LFS condition printed in three shapes by surface. The design names
  the catalogue the contract between Pitloom and the skills
  ([message-catalogue-and-skills.md](../../design/message-catalogue-and-skills.md)).
- **Inventory first, by AST.** 983 emission sites on b18e2cce, 62 families
  over 35 condition words; 31 families cover 80% of sites. The inventory
  tool in #390 counts 993 sites, 567 of them in scope (a line a person sees
  at `WARNING`, `INFO` or `ERROR`) on its branch head 963f8b78. Out of
  scope: DEBUG, `KEY=VALUE` data, pass-through `str(exc)`, a reader's
  detail text (the DETAIL of a wrapper's line), internal invariants.
- **A trailing `[code]` after a space, chosen against two alternatives.**
  The text stays unchanged, so the 453 `in caplog` assertions and the
  matched skill quotes keep passing. Rejected: a `CODE=` pair after the
  subject (155 of 545 templates have no `KEY=` subject) and a leading
  condition word (rewrites every line). Advice is a catalogue field, not
  parsed from the `;` separator, because another tool's own `; ACTION` can
  sit inside a detail. Codes were first to hold dots (`git.too-large`
  existed); the #390 review replaced them with `/`
  ([message-catalogue-decisions.md](message-catalogue-decisions.md)).
- **A code at the end of a line is not trusted by position.** A file named
  `x [lfs-pointer]` makes the uncatalogued `WARNING: skipped x
  [lfs-pointer]` end in a code Pitloom never said. `trusted_message` trusts
  a line only when its code is catalogued, the level is one the entry uses,
  and the text before it matches one of the entry's patterns
  (`messages/_lines.py`, #390).
- **The reader regex matched false codes in Pitloom's own text.** A static
  test lists every string constant ending in a token the line regex reads
  as a code: `[tool.pitloom.content-type]` and `[tool.poetry.dependencies]`
  (TOML table names; dots were then legal in codes). The list could only
  shrink; it is now empty (section 6 of the decisions note).
  Do: when you add an in-band marker, scan your own literals for it.
- **A forwarded code counts as uncoded.** A site that prints the code read
  from an exception at run time (`code_extra_of(exc)`) carries the cause's
  code but states no message itself, so the ratchet
  (`tests/test_message_ratchet.py`, per-module counts that may only fall)
  counts it as uncoded (`scripts/message_inventory/_coded.py`).
- **DEBUG carries no code.** DEBUG is developer-only and never on stderr by
  default; a said-once message repeats at DEBUG without its code, so a code
  appears once per event (`messages/_emit.py`).
- **SARIF.** Decided for 0.23.0: `--report` as JSON Lines with
  SARIF-compatible names (`ruleId`, `level`, `message`, a location from
  `FILE=`), then a SARIF 2.1.0 export. No reviewer report on the ruleId
  mapping was found for these notes; whether a catalogue code is the right
  `ruleId` unit is open (see
  [open-research-questions.md](open-research-questions.md)).

## 3. Skills engineering

- **Progressive disclosure has a cost: a move loses rules silently.** #385
  moved detail into `references/`: `sbom-enrich` 26,181 to 14,756 bytes,
  `sbom-generate` 26,267 to 14,951; the test ratchet became 16 KB and 400
  lines (the specification's limit is 20 KB and 500 lines). A read-only
  review found four kinds of loss: a rule narrowed to its typical case, a
  dropped "relay, do not run the fix", a paraphrase that was false, and a
  vague pointer (da06c942). The false paraphrase: a model whose header
  contradicts its suffix is a `WARNING:` on a project scan (no
  `ai_AIPackage`) but an `ERROR:` (exit 1) for `loom model` and
  `loom enrich`. The original body kept the two apart; the shortened one
  said "no model (`ERROR:`, exit 1)" for every route.
  Do: review a move as a behaviour change, against those four kinds.
- **Every body pointer states a condition.** A bare list of links is read
  always or never; `test_every_body_pointer_says_when_to_read` requires the
  same sentence to say when to read the reference.
- **Prepare before the first run, not after the warning (#392).** Without
  the `licenseid` database a run is thinner (`licenseid` has nothing to
  match licences against); the agent
  fixed it after a `WARNING:` and so ran twice. The skill now runs
  `licenseid update --source packaged` first. Probed: it needs no network,
  creates a missing database, is idempotent (the file's SHA-256 unchanged
  on a current one) and refuses a snapshot older than the database. With an
  ID registry, the thin run rewrites the licence entry; file and package
  ids hold (skills-trigger-coverage.md).
  Do: put an environment check that changes the output before the first
  run of a skill recipe.
