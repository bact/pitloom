---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-26
Last-Modified: 2026-11-26
---

# Message catalogue sweep C2 ("quotes and wording"): plan

See also: [message-catalogue-sweep-plan.md](../implementation/message-catalogue-sweep-plan.md)
(sweep C as first defined, section 3 item 3),
[message-catalogue-sweep-b-plan.md](../implementation/message-catalogue-sweep-b-plan.md)
("Carried to sweep C", "For sweep C"),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the contract),
[message-catalogue-agent-rules.md](../implementation/message-catalogue-agent-rules.md).

Read-only plan. Reference tree 4c194136 (main 4ef7961d plus open #543).
Every count below was measured on that tree; "reproduced" means a probe or
CLI run printed it, "read-only" means read from code or docs only. Sweep C1
(behaviour fixes) and the masking PR run in parallel; overlap in section 9.

## 1. Scope

| Id | What | Where | Evidence | User-visible effect | SBOM / stderr change |
|---|---|---|---|---|---|
| Q1 | 86 backticked `LEVEL:` quotes hold no family marker, so no drift test reads them (the sweep plan said 84) | `tests/messages/test_drift_quotes.py` `_quotes()`; 340 `LEVEL:` quotes in `CLI_DOC_FILES` | reproduced (probe over `CLI_DOC_FILES`) | none until a stale quote is fixed | no / no |
| Q2 | Stale or impossible quotes among them: `INFO: Merge: 'name' on ...` (now `Merge: ELEMENT=...: name replaced by the one the fragments agree on`), `WARNING: skipped x \x5blfs-pointer]` (no uncoded line says that; a relay does: `WARNING: licenseid: skipped x \x5blfs-pointer]`) | `docs/python-api.md:333`, `docs/messages.md:125` | reproduced (catalogue grep; relay escape probe) | docs only | no / no |
| Q3 | 9 markers are no substring of their family's templates; 7 print only with a value filled in (`directory not found: `, `received SIGTERM`), 2 can never match alone: `not valid JSON for ` (non-free `use` field cut mid-value) and `not read: Poetry reads [project]` (`[project]` read as a code) | `test_drift_quotes.py:_MARKERS` | reproduced (`quote_matches(marker, family, marker)`) | none | no / no |
| W1 | `1 seconds`: 9 templates print `%(seconds)s seconds`; `--build-timeout 1` and a sub-second Hub/PyPI timeout (rounded up to 1) print it; 4 tests pin `within 1 seconds` | `build-code-unsafe` x4, `build-timeout` x2, `download-timeout` x3 | reproduced (render; `tests/extract/remote/test_hub_api.py:198`, `test_huggingface_api_timeout.py:129`, `test_pypi_http_fetch.py:285,494`) | stderr wording | no / yes |
| W2 | Other count forms: every other `%(n)s <noun>s` line counts 2 or more by construction (`%(number)s wheels match`, `sdists`, `files have one key`) or a fixed cap (`more than %(number)s redirects`); the rest use `(s)` | `.probe` template scan | reproduced (scan of 610 lines) | none; a lint test keeps it so | no / no |
| S1 | Per-line `since`: `Line` has none. 25 lines are new since v0.24.0 under a code dated earlier (e.g. 9 `input-not-found` lines, `query-no-effect` 0.24.0, `url-unsafe/host-spelling` reworded), so the reference dates them wrong | `messages/_types.py:152`, `scripts/generate_message_reference.py:226,294` | reproduced (v0.24.0 catalogue dump: 140 lines, 138 kept, 2 reworded, 472 new, 25 of them under older codes) | reference pages gain a "Since" note | no / no |
| A1 | `author-invalid` says "not an email address" for an entry whose address is valid but followed by text (`Ann <a@x.org> extra`, `a@x.org trailing`) | `extract/authors.py:_read_entry`, `messages/_authors.py` | reproduced (`author_pairs`) | stderr wording | no / yes |
| A2 | The docs example `AUTHOR_EMAIL=['a', 'b', 'c', ...]: not an email address; 5 entries not recorded` cannot print: `a` holds no `<`, `>` or `@`, so it is a name, never noted | `docs/metadata-provenance-authors.md:104-105` | reproduced (real line: `AUTHOR_EMAIL=['x@y z', 'p@q r', 's@t u', ...]: ...`) | docs only | no / no |
| A3 | A dependency's over-cap author field names no package: `WARNING: FIELD=AUTHOR_EMAIL: larger than the 1000-entry author-field cap; ...` for `requests` | `extract/_author_warnings.py:58` (`warn_field_cap`), `extract/dependency_authors.py:42` | reproduced (`dependency_author_pairs('requests', ...)`) | stderr wording | no / yes |
| D1 | `dataset-conflict` said twice for one dataset and field (reader, then the assembler's fold by name); the catalogue says "Said once per dataset and field" | `core/dataset_merge.py:102` via `extract/ai_model/_gguf_datasets.py:313` and `assemble/spdx3/dataset.py:295` | reproduced (`loom model` on a GGUF with entries d@1 url a, d@1 url b, d@2 url c: `FIELD=download_url` twice) | one line fewer | no / yes |
| D2 | The conflict lines name no model: two in a multi-model wheel cannot be told apart | `messages/_datasets.py` templates | reproduced (same run) | stderr wording | no / yes |
| D3 | The #534 CHANGELOG bullet "dataset lines name `SOURCE=` and `FIELD=`": only `dataset-field-invalid` does; `dataset-conflict` names `DATASET=`, `dataset-name-missing` `FILE=` | `CHANGELOG.md:148-149` | reproduced (catalogue) | CHANGELOG | no / no |
| B1 | Metadata-budget `over-cap` reads as if the model file is over the cap (`FORMAT=gguf FILE=n.gguf: larger than the 10-byte max-source-metadata-bytes cap; ...`), and the dropped-key count of 0.24.0 ("had all %d metadata keys dropped") left the line | `assemble/spdx3/provenance.py:362-365` | reproduced (`loom model --max-source-metadata-bytes 10`; `git show v0.24.0`) | stderr wording | no / yes |
| R1 | `reference-not-found/dataset`: a repeated name warns once per repeat; a non-string value prints quoted like a name (`input_datasets='a value of type int'`) | `_loom_active_run.py:376-407` | reproduced (loom SDK run, 4 lines for `["x","x",5,None]`) | one line per name | no / yes |
| L1 | `line_kind` reads `ERROR: (a log message that could not be shown) [file-unreadable]` as `uncoded`, though the agent rules and `docs/messages.md:23` say it stays coded when its error had a code | `messages/_line_kind.py:101-129` | reproduced | test harness only | no / no |
| L2 | argparse wording with `usage_code() is None` | `messages/_options_say.py:35` | **not reproduced** on 3.10.18, 3.11.12, 3.12.9, 3.13.5, 3.14.3 (11 argparse wordings; the only `None`, "one of the arguments ... is required", needs a required mutually exclusive group, which no `loom` parser has) | none | no / no |
| F1 | `ERROR: spdx3-validate: <line>` quoted without the frame the CLI always prints (`ERROR: loom fragment validate: spdx3-validate: ...`) | `skills/sbom-validate/SKILL.md:113`, `docs/fragments.md:183`, `docs/wheel-sbom.md:79,304` | reproduced (`loom fragment validate` on an invalid document) | docs and skill | no / no |
| K1 | `skills/sbom-generate/SKILL.md:269` "Every stderr line starts with exactly one of `INFO:`, `WARNING:`, `ERROR:`" is false (argparse usage, tracebacks); body 16,381 of 16,384 bytes (enrich 16,374) | `skills/sbom-generate/SKILL.md` | reproduced (`loom project --bogus`: three untagged `usage:` lines) | skill | no / no |

## 2. Out of scope, and where each goes

- **Docs over 30 KB** (`docs/ai-model-formats.md` 44 KB, `ai-model-scan-limits.md`
  39 KB, `git-urls.md` 36 KB, `cli.md` 35 KB, `configuration.md` 32 KB,
  `id-registry.md` 31 KB, `skills/sbom-enrich/references/minimum-elements.md`
  31 KB), `AGENTS.md` (34 KB) and `working-docs/design/roadmap.md` (37 KB):
  one docs-only PR after C2 (splits move anchors that C2's quote edits sit in;
  a split in the same PR doubles the diff). C2 only edits lines in them.
- **git-userinfo quoting** (`extract/remote/_git_credentials.py:144`,
  `quote_source(sanitize_url(...))`): credential text, so the masking PR.
- **`text-malformed` `ELEMENT=`** (`export/spdx3_json.py:143` passes an
  element's *name* as `file=`): read-only (APFS refuses non-UTF-8 names, so not
  reproducible here). Ruling Q8; default: rescan.
- **R1 "forward-only"** (six INFO codes with actor/effect not `none`): record
  the ruling in the rescan; no message changes.
- **`input_datasets` as a string, unhashable entries, wrong-typed loom SDK
  arguments, `Ann <a@x.org> extra` dropping a valid address**: behaviour, C1.
- **Masking items** (`one_line` collapse, request-id glue, `Bearer%20`): the
  masking PR.
- **Matcher anchoring** (a quote starting `LEVEL: ` matches mid-line, since
  `_piece_of` tries every start): measure in step 2; fix only if no more than
  ~5 quotes break, else roadmap.
- **`(s)` everywhere else** (`fragment(s)`, `id(s)`): house style, kept.

## 3. Rulings needed

1. **Split C2 in two PRs?** Options: one PR (~45 files) or C2a "quotes,
   since, kinds" (Q1-Q3, S1, L1, L2, F1, K1) then C2b "wording" (W1, A1-A3,
   D1-D3, B1, R1). **Recommend the split**: C2b's new lines under old codes
   need S1's per-line `since`; each half stays under 30 files and 800 lines.
2. **Plural form for seconds.** (A) `%(seconds)s second(s)` (house `(s)`
   style, no code); (B) a `duration` field whose writer prints `1 second` /
   `30 seconds`, shown `<duration>` (precedent: the `size` field carries its
   unit and already pluralises: `1 byte`, `N bytes`). **Recommend B**: a time limit is read by people, and
   `after 42 second(s)` reads worse than the count lines `(s)` serves; the
   field's shape (`[1-9][0-9]* seconds?|0 seconds`) stays checkable.
3. **What per-line `since` means.** The first release that prints that exact
   text at that level, so a reworded line is new. Default `None` = the entry's
   `since`. Baseline: the v0.24.0 catalogue (the last tag; there is no
   v0.24.1 tag here though the skills say "0.24.1": **confirm**). Shown as a
   `- **Since**:` bullet only for lines that differ from the code's. Recommend
   all three.
4. **Quoting frames.** (A) A coded quote may leave its frame out (the code
   names it), but an uncoded quote a reader matches by text (relay, summary)
   shows the frame the line prints, as `ERROR: loom <command>: spdx3-validate:
   <line>`; (B) every quote shows its frame. **Recommend A**: it is what 250+
   checked quotes already do and the matcher allows; B would touch every
   `ERROR:` quote. One sentence in `docs/messages.md` and both skills'
   `references/messages.md` states it; the reverse scan enforces the relay
   half.
5. **`dataset-conflict` said twice.** (A) one memo per model: the reader
   records the fields it said on each `DatasetReference`
   (`said_conflicts: frozenset[str]`), and the assembler seeds its `warned`
   set from them, so the summary "once per dataset and field" holds; (B) keep
   both lines and add `kept`/`dropped` values (as `fragment-conflict`), and
   change the summary. **Recommend A**: the summary is the contract; the
   version fold line (a different field) still says the dropped release.
6. **Model subject for `dataset-conflict`.** `FILE=<model file> DATASET=...`
   (the subject vocabulary; reader has `where`, the assembler the model's
   `physical_path`/`file_name`) or `MODEL=<name>` (used once today, by
   `usage-unparseable/mention`, for a model file name). **Recommend `FILE=`**,
   with the model's name when it has no file (loom SDK model): then
   `MODEL=`. Needs both lines in the catalogue.
7. **`author-invalid` wording.** (A) one condition for every entry: "not one
   valid email address" (true for `x@y z` and `Ann <a@x.org> extra`); (B) a
   variant line for text after a valid address. **Recommend A**: the line is
   per field and lists entries of mixed causes; B cannot be one line per field.
8. **`text-malformed` `ELEMENT=`** in C2b or the rescan? **Recommend the
   rescan**: not reproducible on macOS; `ELEMENT=` holds an spdxId elsewhere
   but this site has a name, so it also needs a subject ruling.
9. **`line_kind` of an unshown message with a code.** (A) `coded` when the
   text is exactly `UNSHOWN_MESSAGE` (after at most one frame allowing the
   code at that level) and the code is catalogued at that level; (B) a new kind
   `unshown`. **Recommend A**: the docs and agent rules already say it is
   coded; B adds a kind every consumer must learn.
10. **R1 repeats.** Say each missing name once per output dataset, in first
    order. If C1 refuses non-`str` entries at the call, C2b drops the
    `a value of type` branch; if not, keep it. **Recommend** C1 owns
    `_loom_active_run.py` and folds the dedup in (one file, one PR).

### Rulings recorded (maintainer, 2026-11-26)

Every recommendation accepted, with one change to ruling 1:

1. **Split.** C2a = Q1-Q3, S1, L1, L2, F1, K1 **plus W1 and W2** (the
   `duration` field and its count-plural lint move here from C2b); C2b = A1-A3,
   D1-D3, B1 (R1 goes to C1, ruling 10).
2. **B**: a `duration` field printing `1 second` / `N seconds`.
3. **Accepted**: per-line `since` = first release printing that exact text at
   that level; baseline the v0.24.0 tag (no v0.24.1 tag exists); `Since`
   bullet only where a line differs; released-lines fixture refreshed at each
   release bump.
4. **A**: a coded quote may omit its frame; an uncoded quote matched by text
   (relay, summary) shows the frame it prints.
5. **A** (C2b): one memo per model (`said_conflicts` seeds the assembler).
6. **`FILE=`** (C2b), `MODEL=<name>` for a model with no file.
7. **A** (C2b): "not one valid email address".
8. **Rescan**: `text-malformed` `ELEMENT=` stays out of C2.
9. **A**: an unshown message with a code catalogued at that level is `coded`.
10. **C1 owns R1's dedup** in `_loom_active_run.py`.

## 4. Design per item

**Q1-Q3, reverse quote scan (C2a).** A new module
`tests/messages/test_drift_quote_kinds.py` (the existing file is 684 lines)
scans every inline span holding `(ERROR|WARNING|INFO): ` in `CLI_DOC_FILES`
and classifies it, first match wins, through one helper `quote_kind(quote)`
in `tests/_message_drift.py` (437 lines; if it crosses ~480, move the quote
helpers to `tests/_message_quotes.py`):

| Class | Count now | Check |
|---|---|---|
| marked (a family marker) | 254 | unchanged: `test_a_quote_is_a_piece_of_the_catalogue` |
| coded (ends `[code]`, no marker) | 13 | `quote_matches` against the code's own entry, marker = each core (`cores()`) of its lines; a quote with no literal text (`WARNING: ... [credentials-unsafe/written]`) checks level and code only |
| catalogued, no marker, no code | 7 (`... content changed ...` x2, `... content not checked`, `... registered for both ...`, `FILE=<file>: AI models ... listed without metadata ...` x2, `PYPI=<name> FILE=<file>: ...; skipped`) | `quote_matches` against every family, accepted when exactly one family's line holds it with a literal run of 12+ characters; else fail and add a marker |
| prefix (a frame or sub-prefix, then nothing, `...` or one placeholder) | 31 | its text is the start of a frame, a template or a summary at that level (anchored `_piece_of`, new `anchored=True`) |
| summary | 17 | a piece of a `SUMMARIES` template (same matcher; `N`, `NAME`, `KEY` read as wildcards, which `_WILD` gains) |
| relay | 12 | a `RELAY_PREFIXES` prefix after at most one frame of that level; at `ERROR`, a frame or `loom <command>: ` must precede it (ruling 4) |
| detail | 1 | `INFO: KEY=<v> ...` (`line_kind`'s `_DETAIL` shape) |
| external | 3 | `_EXTERNAL` allowlist, shrink-only, each with its tool: `WARNING: popularity.csv: missing` (LicenseID's `update`), `ERROR: JSON Schema validation failed for <file>:` and `ERROR: SHACL Validation failed for <file>:` (spdx3-validate run by hand; both strings verified in the installed packages) |
| stale / illustrative | 2 | fixed in the docs (Q2), no class |

A meta-test pins the class counts' total to the scan (no quote unclassified)
and that `_EXTERNAL` entries still occur. Q3: a test that every marker can
print, `quote_matches(m, family, m)`; lengthen the two markers
(`"not valid JSON "`, `"not read: Poetry reads"`). Docs edits: `python-api.md`
(the `Merge:` quote), `messages.md:125` (a relay example),
`skills/sbom-enrich/references/dangling-references.md` (`is registered for
both`) as the scan demands.

**S1, per-line `since` (C2a).** `Line.since: str | None = None`; checked in
`Message.__post_init__` (release grammar, not earlier than the entry's).
`Line.effective_since(message)` is the one accessor. 25 lines set
`since="0.25.0"` (list from the probe, in the build brief). The generator adds
`- **Since**: <code since>; line N: 0.25.0` after **Lines** only when a line
differs (about +60 bytes per affected code; `message-codes-targets.md` is
27,547 bytes, gains three notes: stays under 30,000). Baseline fixture
`tests/fixtures/message-catalogue/released-lines.tsv` (code, level, template;
140 rows from v0.24.0), written by a `--snapshot` option of
`scripts/generate_message_reference.py`; the release-bump step regenerates
it (add to the release checklist in `CONTRIBUTING.md`).

**W1, `duration` field (C2b, ruling 2).** `_fields_*.py` gains `duration`
(writer `plural_seconds(n)`; the `seconds` field goes if nothing else uses
it); the 9 templates drop the literal ` seconds`; per-line `since` 0.25.0 for
the lines of 0.22-0.24 codes (`download-timeout`, `build-*`). Callers pass
`duration=` through their say-helpers (`_build_say.py`, `_remote_fetch.py`
sites: grep `seconds=`). **W2**: a lint test in
`tests/messages/test_messages_types.py`: no template has
`%(<count field>)s <word>s` unless the line is in a short allowlist with its
reason (count 2 or more, or a cap).

**A1-A3 (C2b).** A1: `author-invalid` templates read `not one valid email
address`; summary and advice follow. A2: replace the docs example with the
reproduced line. A3: `author_pairs(..., package: str | None = None)` passes
`package` into `_Report` and `warn_field_cap`, which prints a new `over-cap`
line `PACKAGE=%(package)s %(key)s=%(name)s: larger than ...` (since 0.25.0)
and keys its once-memo on `(package, key, digest)` so a second package with
the same field text is still said.

**D1-D3 (C2b, rulings 5 and 6).** `DatasetReference` gains
`said_conflicts: frozenset[str] = frozenset()`, set by one helper in
`_gguf_datasets.py` from the reader's `warned` set; `merge_dataset_references`
seeds `warned[key]` with the union over the references of a name. Every
`DatasetReference(...)` call site is listed first (AGENTS: a dataclass field
set at every constructor). Templates gain the model subject; summary unchanged.
D3: reword the #534 bullet to "dataset field lines name `SOURCE=` and
`FIELD=`; a dataset conflict names the model" in the same Unreleased block.

**B1 (C2b).** Two new `over-cap` lines (since 0.25.0), said by one helper in
`assemble/spdx3/provenance.py`:
`FORMAT=.. FILE=..: its metadata does not fit the %(limit)s-byte %(purpose)s
cap even with no key; artifact-metadata annotation left out` and
`...: all %(number)s metadata key(s) left out to fit the %(limit)s-byte
%(purpose)s cap`. `_EMPTIED` goes.

**L1 (C2a, ruling 9).** In `line_kind`, after `trusted_message` fails: a line
whose text is `[frame]UNSHOWN_MESSAGE [code]`, the code catalogued with a line
at that level, is `coded`. `UNSHOWN_MESSAGE` is imported from
`log_masking.py` (no edit there). Drop the now stale allowance in
`tests/test_credential_deep_query_surfaces.py:125` if it only covers that case.

**L2 (C2a).** No kind. Add `ambiguous` and `explicit argument` cases to
`test_the_parser_line_is_framed_coded_and_trusted`
(`tests/messages/test_options.py:128`), which runs the real parser on every CI
interpreter: a Python that rewords argparse then fails there, not silently.

**F1, K1 (C2a).** Quote the relay with its frame in `sbom-validate/SKILL.md`
(12,464 bytes, room), `docs/fragments.md`, `docs/wheel-sbom.md` x2. In
`sbom-generate/SKILL.md`, cut "Check stderr" to: Pitloom's own lines start
`INFO:`, `WARNING:` or `ERROR:` (argparse usage text and a traceback are
untagged); scan after every call; pointer to `references/messages.md`, which
holds the moved detail (22,524 bytes now). Net body change must be negative;
the enrich body is not touched. No command or flag changes, so no frontmatter
`description` change and the skills-trigger-coverage audit is unaffected
(note it in the PR).

## 5. Tests per item (each fails on 4c194136)

| Item | Test (file) | Input | Assertion | Marker |
|---|---|---|---|---|
| Q1 | `test_every_level_quote_has_a_kind` (`test_drift_quote_kinds.py`) | the docs tree | no span unclassified; fails on base (2 stale) | none |
| Q1 | `test_quote_kind_boundaries` | synthetic quotes: a coded quote with a wrong level, a wrong code, a prefix that starts no line, a relay at `ERROR` without frame, a summary with a wrong noun | each refused; one accepted twin per case | none |
| Q3 | `test_every_marker_can_print` | `_MARKERS` | `quote_matches(m, f, m)`; fails for 2 on base | none |
| S1 | `test_a_line_new_since_the_last_release_says_so` (`test_messages_types.py`) | fixture vs `MESSAGES` | a line absent from the fixture has `effective_since` > 0.24.0; a present one keeps its; fails for 25 on base | none |
| S1 | `test_line_since_rules` | `Line(since="0.21.0")` under a 0.22.0 entry, `"0.25"`, `"v0.25.0"` | `ValueError` | none |
| S1 | generator snapshot | `--check` | "Since" bullet present for `input-not-found` | none |
| W1 | `test_a_duration_of_one_is_singular` | `duration` writer 0, 1, 2, 604800 | `0 seconds`, `1 second`, `2 seconds`; existing `within 1 seconds` asserts become `within 1 second` | none |
| W1 | CLI: `--build-timeout 1` | B1 manual check, plus `tests/messages/test_build_surfaces.py` at 1 | `after 1 second (` | `platform` (process) |
| W2 | `test_no_count_noun_plural_without_reason` | all templates | allowlist exact | none |
| A1 | `test_text_after_a_valid_address_is_not_one_address` (`tests/messages/test_authors.py`) | `Ann <a@x.org> extra` | line reads `not one valid email address` | none |
| A2 | covered by Q1 (the quote must match) | | | |
| A3 | `test_a_dependency_field_over_the_cap_names_its_package` (`tests/extract/test_authors.py`) | two packages, same over-cap text | two lines, each `PACKAGE=`; once each | none |
| D1 | `test_a_dataset_field_conflict_is_said_once_per_model` (`tests/extract/ai_model/test_gguf_datasets.py`) | the three-entry GGUF above, read then `build_model` | one `FIELD=download_url` line, one `FIELD=version` | none |
| D2 | same file, two models in one wheel (`tests/messages/test_datasets_sites.py`) | two GGUFs with one conflict each | lines differ by `FILE=` | `platform` (wheel archive) |
| B1 | `tests/assemble/test_annotation_metadata_truncation.py` | budget 10, then a budget that drops all keys | new texts with `all <n> metadata key(s)` | none |
| R1 | `tests/core/test_loom_output_input_relationships.py` | `["x","x"]` | one line | none |
| L1 | `tests/messages/test_line_kind.py` | unshown + catalogued code (framed, unframed), + code at the wrong level, + uncatalogued code, no code | `coded`, `coded`, `uncoded` x3 | none |
| L2 | `tests/messages/test_options.py` | `--debu` style ambiguity, `--flag=1` on a store_true | coded `option-invalid` | none |

Cross-surface: W1 on CLI and library (`BuildOptions(timeout=1)` library route;
the hook reads `build-timeout` from config: one hook test); D1 on `loom model`,
`generate_model_sbom()` and the hook (a project holding the GGUF);
B1 on the CLI flag, the library parameter and the `pyproject.toml` key; A3 on
`loom env` and the library env route.

## 6. Build steps and agents

C2a (after C1's `logging_config.py` split lands, or rebased onto it):

1. Haiku: inventories into the build brief, no edits. The 86-quote table by
   class, the 25 per-line-`since` lines, every `seconds=` caller, every
   `DatasetReference(` call site, every doc quote of the changed lines.
2. Opus: S1 (`messages/_types.py`, generator, fixture, `CONTRIBUTING.md`
   release note, the 25 catalogue lines) and L1 (`messages/_line_kind.py`,
   `tests/messages/test_line_kind.py`). Design-heavy; touches the contract.
3. Sonnet, after 2: Q1-Q3 to the spec of section 4. Fence:
   `tests/messages/test_drift_quote_kinds.py` (new), `tests/_message_drift.py`
   (or `tests/_message_quotes.py`), `tests/messages/test_drift_quotes.py`
   (markers only), the docs lines the scan flags.
4. Sonnet, parallel with 3: F1, K1, L2. Fence: `skills/*/SKILL.md`,
   `skills/*/references/messages.md`, `docs/messages.md`, `docs/fragments.md`,
   `docs/wheel-sbom.md`, `tests/messages/test_options.py`.
5. Regenerate pages; Gate A; fresh Opus review; mutation (Gate B).

C2b (after C2a merges, and after C1 if C1 owns `_loom_active_run.py`):

6. Opus: D1/D2 (`core/dataset_merge.py`, `core/dataset_metadata.py` (`DatasetReference`, 3 call sites),
   `_gguf_datasets.py`, `assemble/spdx3/dataset.py`, `messages/_datasets*.py`)
   and B1 (`assemble/spdx3/provenance.py`, `messages/_over_cap*.py`): shared
   state and new subjects.
7. Sonnet, parallel with 6: W1/W2 (fields, 9 templates, say-helpers, tests),
   A1-A3 (`messages/_authors*.py`, `extract/authors.py`,
   `extract/_author_warnings.py`, `extract/dependency_authors.py`). Fence
   excludes `messages/_over_cap*.py` (step 6 owns it: A3's new `over-cap` line
   is added by step 6 to its spec).
8. Haiku: stale-wording sweep (`grep` old texts in `docs/`, `skills/`,
   `tests/`, `scripts/manual_cli_checks/`), CHANGELOG, D3.
9. Regenerate; Gate A; fresh Opus review; mutation; Gate B.

## 7. Gates

- **Tier 1** between rounds: touched tests (`-k`), `ruff`, `mypy`,
  `pyrefly check`, `python -m scripts.message_inventory --check`,
  `python scripts/generate_message_reference.py --check`, a stderr diff of the
  probe runs above against main.
- **Gate A**: full suite `-n 4`; every CI linter (`ruff format`, `ruff check`,
  `pylint examples/ src/ tests/ tests/*/`, `mypy`, `pyright`, `pyrefly check`,
  `bandit -r`, `flake8`); branch coverage of changed files; inventory and
  reference checks; `tests/test_message_ratchet.py` (no rise); each new
  regression test run with `-o pythonpath=` against the base tree, failing.
- **Gate B**: mutation on `quote_kind` (each class branch, the anchored
  flag), `Line.__post_init__`'s since check (`<` vs `<=`), the `duration`
  writer (0/1/2), `line_kind`'s unshown branch (level and catalogue
  conditions), `merge_dataset_references`' seeding, `warn_field_cap`'s
  once-key; manual checks `--only 5,7,17,20,22,25,B1,B6,B7` (C2b) and
  `--only 5,7,4b --network` (C2a, the validate relay); Windows dry run: the
  fixture TSV read with `newline=""`-safe parsing and LF-only, a `FILE=` model
  path with backslashes through the dataset subject (`quote_source`), no new
  path tests otherwise; fresh read of each changed `SKILL.md` in full; label
  `test-all-os` on C2b (wheel and build tests).

## 8. Risks, ranked, and size

1. The reverse scan's "catalogued, no marker" class accepts a quote too
   easily (free fields swallow text): mitigated by the 12-character literal
   rule and the boundary tests; mutation on it.
2. The shared dataset memo misses a route that builds `DatasetReference`
   (card, Croissant, loom SDK): inventory first, count test across routes.
3. Per-line `since` baseline wrong if 0.24.1 was released from another
   branch: ruling 3 confirms.
4. `sbom-generate` body cap: the stderr rewrite must shrink the body; the test
   fails at 16,385 bytes.
5. Generated page sizes: targets 27.5 KB, values 26.9 KB; the `duration`
   field adds one row to values.
6. CHANGELOG conflicts with C1 and the masking PR (one Unreleased block).

Size: C2a about 600 changed lines of src and tests (fixture and generated
pages excluded), ~24 files; C2b about 650 lines, ~28 files. One PR would be
~45 files: over the cap, hence ruling 1.

## 9. Overlap with C1 and the masking PR

- `logging_config.py`: C2 does not edit it (L1 reads `UNSHOWN_MESSAGE` from
  `log_masking.py`). Merge order: C1 (split), masking (`one_line`), then C2a.
- `_loom_active_run.py`: C1 (string `input_datasets`, `abspath`, cwd) owns
  it; R1's dedup goes to C1 (ruling 10).
- `extract/authors.py`: C1 may change what `Ann <a@x.org> extra` records; C2b
  changes only the warning's wording and the cap warning's subject. Land C1
  first; C2b rebases.
- `docs/messages.md`, both `references/messages.md`: the masking PR may edit
  the masking prose; C2a edits the frame and unshown sentences only.
- `_git_credentials.py` (git-userinfo quoting): masking PR only.
- `CHANGELOG.md`: each PR adds to the Unreleased block; C2 folds its lines into
  the existing #527/#534 bullets where the code is new in 0.25.0.

## 10. C2a as built: deviations and known limits

- Helpers moved to `tests/_message_quotes.py` (`quote_kind`, anchored
  matcher); the generator's helpers to `scripts/message_reference/`
  (`frames`, `sections`, `snapshot`). The release step lives in
  `working-docs/implementation/release-checklist.md`, not `CONTRIBUTING.md`.
- `quote_kind` is stricter than section 4's table: a coded quote is matched
  on its longest literal run, a catalogued quote's 12-character run must be
  template text, a prefix quote's values match only as wildcards, a summary's
  run may not sit in a free value. The marker `": not valid JSON "` (not
  `"not valid JSON "`, which marked a value-only quote).
- One `whole_seconds()` rounds every time limit up to a whole second, at
  least 1 (git used `round`; production passes 600.0, unchanged).
- Known limits, not fixed: a stale word between two wildcards
  (`git <command> stale ... did not finish`) still reads as a piece of the
  line (matcher design); `test_count_plurals.py` checks only the word right
  after a count field (`%(number)s Python files` would pass); `quote_kind`
  requires a frame on an `ERROR` relay, `line_kind` does not (true today:
  the only `ERROR` relay is framed by the CLI command).
