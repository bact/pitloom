---
Created: 2026-11-23
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 15 (fragments): tests, steps, gates, risks

See also: [message-catalogue-pr15-plan.md](message-catalogue-pr15-plan.md)
(counts, sites, probes, contradictions, design, rulings Q1 to Q16),
[message-catalogue-pr14-build.md](message-catalogue-pr14-build.md) (the
shape this file follows), [message-frames-forward.md](message-frames-forward.md).
Reference tree: `main` at a45f9baf. Section numbers continue the plan's.

## 6. Files and sizes

New (each under 300 lines, I):
- `src/pitloom/messages/_fragments.py`: the read, document, missing and
  digest entries (`fragment-unreadable`, `-invalid`, `-unusable`,
  `-missing`, `-digest-invalid`, `reference-not-found`).
- `src/pitloom/messages/_fragments_merge.py`: `MERGE_PREFIX`, the conflict
  entries (`fragment-conflict`, `-id-conflict`, `-hash-conflict`,
  `generated-value-conflict`) and the four summaries.
- `src/pitloom/messages/_fragments_say.py`: `warn_fragment_unread`,
  `warn_same_document`, and the conflict say-helpers that take an element
  and a value (so `describe_value` stays in `pitloom.export`).
- `src/pitloom/messages/fragments.py` (public), `_fields_fragments.py`.
- `docs/message-codes-fragments.md` and `skills/*/references/messages-fragments.md`
  (generated).

Edited: `_topics.py` (topic `fragments`, ten families), `_catalogue.py`,
`__init__.py`, `_input_not_found.py` (Q6, C7), `mkdocs.yml` nav,
`scripts/message_inventory/_scope.py` (`FragmentReadError` in
`DETAIL_EXC`), the twelve source modules of the plan's section 0, and
`_fragments_read.py`, `_fragments_refs.py` (sort), `_generators_merge.py`
(Q2), `core/_config_parse_fragment.py` (Q8).

Over a limit before PR 15: `tests/assemble/test_fragments_generated.py`
851 lines (split first if touched), `tests/cli/test_cli_fragment_list.py`
504, `tests/messages/test_drift_quotes.py` 538 (one marker line each),
`src/pitloom/assemble/spdx3/fragments.py` 519 (shrinks: two text builders
and their `__all__` entries go).

## 7. Tests (one per boundary, mutation-sensitive)

New test files:
- `tests/messages/test_fragments.py`: entries, lines, fields, `SAMPLES`,
  every template through `template_problem`; each required twin differs
  from its optional line only in the outcome.
- `tests/assemble/test_fragments_read_stages.py`: one case per stage and
  cause: missing permission (POSIX, by `chmod`; Windows by a directory
  named `x.json`, `IsADirectoryError` or `PermissionError`); a UTF-8 BOM
  (merges, V); UTF-16 with a BOM (merges, V);
  truncated UTF-16 (`json`); `{not json`; a top-level array (`spdx`);
  nesting over the recursion limit (`json`); `{"a":1}` (`spdx`); `2**60`
  and `1e400` (`spdx`, the RFC 8785 check); `InternalError` and
  `MemoryError` from the deserialiser propagate (patch the module's own
  name). Each asserts the stage, so a classifier reordered (both
  `JSONDecodeError` and the RFC 8785 errors are `ValueError`) fails.
- `tests/messages/test_fragments_surfaces.py`: per family, the CLI
  (`loom project`, `loom merge`, `loom fragment list`: stderr line,
  `[code]`, exit code), the library (`merge_fragments`,
  `generate_project_sbom`, `generate_merged_sbom`: `caplog` record
  `pitloom_code`, `FragmentMergeError.pitloom_code` for F2 and F5) and the
  hook (`staged_sbom` stderr ERROR with `[fragment-missing]`). Required and
  optional, one test each.
- `tests/messages/test_fragments_hostile.py`: untrusted text in a key, a
  value, a name, an spdxId and a configured path: `\n`, `\r`, `\x1b[31m`,
  `::error::`, `https://u:s3cret@h/`, `ghp_` + 36 characters, a fake
  trailing ` [over-cap]`; result: one masked line per record and
  `trusted_message` true only for the real code. A 10 MB conflicting
  `description` prints at most the 120-character excerpt (S7).

Regressions (each must fail on a `git archive` of `main`, PYTHONPATH
pinned):
- S1: three files, one unreadable: `merge: merged 2 fragment(s)`.
- S2 (Q1): every fragment unreadable: exit 1, no output file, no E1.
- S4 (Q10): a required fragment holding `2**60`: `fragment list` exits 1
  and says `fragment-invalid`, as `loom project` does.
- S5: six dangling relationships print sorted by id; reversed input order
  gives the same lines.
- S9 (Q8): `sha256 = "00"` is `config-invalid`; `"ABC..."` (64 upper-case
  hex) lists `SHA256=match` against the lower-case digest.
- S10 (Q9): L7 carries `[metadata-invalid]`.

Boundaries (one test each; the "A and B" rule):
- `_merge_scalar`: empty canonical takes the value silently; the same JSON
  in another spelling stays DEBUG; a path-suffix name stays DEBUG; a real
  difference is one `fragment-conflict`; `kept` is the earlier source in a
  project merge (the project's) and in `loom merge` (the earlier file).
- `_merge_colliding_entry`: empty kept value filled silently; equal and
  same-JSON quiet; different: the keyed line.
- `rename_id_clash`: another type (line 1); same type, disjoint digests
  (line 2); digests differing in case or algorithm only: no line.
- `warn_if_same_name_different_hash`: no line when the id already
  conflicted (`id_conflict` true) and one when not; no line when either
  side has no SHA-256.
- G1: no line when the old value is empty or a respelling; G2: one line on
  a rename, none on a path-suffix name; G3: one line only when the comment
  or an Annotation lost the entry.
- `fragment-missing`: the configured paths in configuration order; the
  number equals the paths listed; with zero required fragments unmet no
  raise.
- `fragment-unusable`: a fragment with no `SpdxDocument` never matches;
  `fragment list` with an unresolvable project id prints `SAME_DOCUMENT=-`
  and no F4 line.
- Summaries: `fragment validate` count with 2 paths; L8 with an empty
  `files = []` (present but empty: still "no fragments configured").

Drift: `tests/_message_drift.py` `SAMPLES` (new fields),
`test_drift_quotes.py` one marker per new family (ten), the S6 manual
check's pin. Platform: classify each new file (`-m platform
--collect-only -q`); the read-stage and surface files are
`pytestmark = pytest.mark.platform`; label the PR `test-all-os`.

Windows dry-run notes (put in every brief):
- A configured path is shown as written (Q6): `frags/bad.json` stays with
  `/` on Windows; a `loom merge` name joins the given directory with
  `Path`, so `dir\name.json`; assert with `str(Path(...))`, never a literal
  `/`.
- Unreadable fragment: no `chmod` on Windows; use a directory named
  `x.json` for a configured path (`IsADirectoryError` on POSIX,
  `PermissionError` on Windows: both stage `read`).
- `write_bytes` for every fixture whose digest is asserted (CRLF).
- `tempfile.gettempdir()`, never `/tmp`; `PureWindowsPath` for the shown
  path test.

Mutation targets (Gate B): the stage classifier's order; `except
InternalError`/`MemoryError: raise`; the required/optional line choice;
`sorted` in `_find_dangling_references`; `id_conflict` gate before U4;
`_is_empty(old)` before G1; the merged count passed to M1; the digest's
`.lower()`; the `bool(same_document)` exit choice in `_report_fragment`.

## 8. Steps and agents (branch from fresh `origin/main`, created by the user)

Before step 1: `git log --oneline -3`; `--check` passes at 108 (or what
the Q1 fix PR left).

**Step 0 (Q1, ruled 2026-11-23: in this PR, not a separate PR)**: folded into step 1 (the raise is born coded) and step 2 agent A; formerly "the fix PR", Sonnet with an Opus review: the
empty-merge raise (uncoded `ValueError` there, coded in PR 15), a
regression test, CHANGELOG. Ratchet: +1 for the new raise unless it is
born coded (then step 1 below adds the line first; prefer born coded, as
#486's `unpinned`).

**Step 1, Opus (core: untrusted text, the classifier, coded exceptions).**
One commit. Fence: `src/pitloom/messages/**`, `_fragments_read.py`,
`fragments.py` (`FragmentMergeError`, `_load_fragment`, the dangling
raise), `_fragments_refs.py`, `scripts/message_inventory/_scope.py`,
`tests/messages/test_fragments.py`, `mkdocs.yml`. Work: entries, fields,
`SAMPLES` stubs, `FragmentReadError` and the say-helpers, the value
wrapper (4.4), `--write` the reference, Tier 1 (`pytest tests/messages
tests/core/test_fragments_read.py -n 4`, mypy on touched files), the
import-cycle test both ways. Export the names to the Sonnets.

**Step 2, three Sonnets in parallel.** Common brief: read CLAUDE.md;
British English; ASCII in comments; no `%r`, no raw `exc`; messages only
through `emit`/the helpers; never edit generated pages or the baseline; no
git writes; no `sed -i` (use Edit); touched tests only; report every
changed stderr text; the Windows notes.

| Agent | Fence | Brief |
| - | - | - |
| A (conversions) | `_fragments_props.py`, `_fragments_ids.py`, `_fragments_hashes.py`, `_fragments_generated.py`, `_fragments_model_names.py`, `_fragments_evidence.py`, `_fragments_envelope.py`, `_generators_merge.py`, `cli/commands/{merge,fragment,enrich}.py`, `core/_config_parse_fragment.py`; pinned tests under `tests/core/test_fragments_*`, `tests/assemble/test_fragments_*`, `tests/cli/test_cli_{merge,fragment,fragment_list}.py`, `tests/test_fragment_generated_surfaces.py`, `tests/test_loom_model_name_surfaces.py`, `tests/messages/test_input_not_found.py`, `scripts/manual_cli_checks/_sequences.py` (S6) | U1 to U4, G1 to G3, M1, L1 to L8, N1, Q8, Q10; split `test_fragments_generated.py` first if touched |
| B (docs, skills) | `docs/fragments.md` (48-52, 59, 85-99, 111-121), `skills/sbom-enrich/references/examples.md` (242-258, 317), `skills/sbom-generate/references/id-registry-log-lines.md` (119-129), `skills/sbom-enrich/references/minimum-elements.md` (212-215), `skills/sbom-enrich/SKILL.md` (223-231: name `[reference-not-found]`), `skills/sbom-enrich/references/pre-merge-check.md` (15-19), `skills/sbom-validate/SKILL.md:111` (unchanged text, check), `CHANGELOG.md` | Rewrite each quote to the regenerated page's text with `[code]`; a fresh read of each changed `SKILL.md` (no description change: no new command or flag) |
| C (new tests) | the section 7 files, `tests/_message_drift.py`, `test_drift_quotes.py` | Section 7; fail-on-base per regression; short `ids=`; classify each file |

**Step 3, Haiku sweep** (after A; tests outside the fences; no `src/`):
grep `tests/` and `scripts/` for `Failed to read SBOM fragment`, `merge
will fail`, `document being merged into`, `Merge: `, `shares spdxId`,
`two different SHA-256`, `dangling reference`, `could not be merged`,
`creation time`, `SHA-256 mismatch`, `fragment list: `, `register the
fragment`, `_fragment_read_failure_message`, `_same_document_message`.
Known (V): 17 test files hold one of them (`Merge: ` 10 files, `dangling
reference` 4, `shares spdxId` 6). Update and run each file; report any
touched file over 450 lines.

**Step 4, Opus: integrate.** `--write`; `--write-baseline` (expect 85,
section 0); page sizes under 30,000 B; the stderr sweep (8.1); review round
1 (a fresh-context Opus, diff only, with the Windows notes), batch fixes;
round 2 re-checks round 1's fixes; Gates A and B; working docs.

### 8.1 Stderr sweep (HEAD versus the tree, offline)

Cases (the probes of plan section 2, rebuilt in the scratchpad): `loom
merge` of the 8-file directory (4 bad), of an all-bad directory, of a
dangling directory (6 references), of a conflict pair; `loom project` with
bad, missing, self and big-number required fragments; `loom fragment list`
of the same project and of one with an unreadable `[project]`; `loom
fragment validate` of a valid SBOM; `loom enrich` on a model; the hook
(`hatch build -t wheel` on a fixture with one required bad fragment).
Expect: identical SBOM bytes (`--creation-datetime 2026-01-01T00:00:00Z`)
and exit codes, except S2, S4 and Q8's decided changes; every changed line
gains `[code]` and the decided wording.

## 9. Gates

Tier 1 between rounds: touched tests `-n 4 --lf`, linters on touched
files, `--check`.

Gate A, from the worktree root (read every exit code directly, never
through `| tail`):

```shell
export PYTHONPATH="$PWD/src"
PY=/Users/arthit/projects/pitloom/.venv/bin/python
$PY -m ruff format examples/ src/ tests/
$PY -m ruff check --fix examples/ src/ tests/
$PY -m flake8 examples/ src/ tests/; echo "flake8=$?"
$PY -m pylint examples/ src/ tests/ tests/*/; echo "pylint=$?"
$PY -m mypy examples/ src/ tests/; echo "mypy=$?"
/Users/arthit/projects/pitloom/.venv/bin/pyright --pythonpath "$PY" examples/ src/ tests/; echo "pyright=$?"
/Users/arthit/projects/pitloom/.venv/bin/pyrefly check --python-interpreter-path "$PY" examples/ src/ tests/; echo "pyrefly=$?"
$PY -m bandit -r src/pitloom; echo "bandit=$?"
$PY -m scripts.message_inventory --check; echo "ratchet=$?"
$PY scripts/generate_message_reference.py --check; echo "reference=$?"
$PY -m pytest tests/ -n 4; echo "pytest=$?"
$PY -m pytest tests/messages tests/core tests/assemble tests/cli -n 4 \
  --cov=pitloom --cov-branch --cov-report=term-missing \
  | grep -E "messages/(_fragments|fragments|_fields_fragments|_input_not_found)|spdx3/(fragments|_fragments_)|commands/(merge|fragment|enrich)|_generators_merge"
$PY scripts/manual_cli_checks --only '2,7,S6,M/completeness'; echo "manual=$?"
```

Use an absolute `PYTHONPATH` (a relative one imports another checkout);
build the licence database first if tests fail on `main` too; delete
`pytest-of-*` after runs.

Gate B: mutation testing (section 7 targets, each mutant with its module's
tests only); `scripts/manual_cli_checks -j 8` in full; determinism and the
Windows dry-run; a fresh-context sweep agent; a fresh read of
`skills/sbom-enrich/SKILL.md` and its changed references; `gh pr view <n>
--json labels` shows `test-all-os`, and `Unit tests` and `Build wheels`
ran on the head commit after the label.

Docs, working docs and ledgers:
- Regenerate the new page and its skill twins, and `targets` (Q6, C7).
- CHANGELOG: fold into the catalogue bullet with the PR link; S1, S2, S4,
  S5 as one Fixed bullet if they ship here.
- Migration row 15 (actual counts and families, C1); frames-forward "PR
  15" marked built (C4, C5); review rounds: the next round; roadmap and
  known-bugs: S3 (Q11), the spdx3-validate relays for PR 16, Q13's
  dataset lines for PR 17.
- Format-gap ledger: none (no SBOM field changes).
- No CLI flag changes: no `_matrix_plan.py` entry, no skill description
  change.

## 10. Risks (ranked) and unknowns

1. **Attacker text in the exception relay.** The deserialiser quotes keys
   and values; `failure_text` must mask, escape and cut before the line is
   built, and a fake `[code]` inside must not be trusted. Mitigation: the
   hostile test file; `trusted_message` asserts.
2. **A classifier that misfiles a stage.** `JSONDecodeError`,
   `UnicodeDecodeError` and the RFC 8785 errors are all `ValueError`; the
   stage must come from where it was raised, not the type. Mitigation:
   stage-tagged raises in `read_fragment_set`, one test per stage.
3. **`InternalError` or `MemoryError` swallowed by the broad catch** in
   `_load_fragment` and the list. Mitigation: re-raise first; a test each.
4. **Q9's `InternalError` on an uncoded metadata failure** could crash
   `fragment list` where it warned before. Mitigation: the probe over PR
   12's corpus; the alternative in Q9.
5. **Pins outside the fences.** 17 test files and the S6 manual check.
   Mitigation: the Haiku sweep and the full suite.
6. **Value rendering (4.4).** Double quoting or an import cycle from
   `describe_value`. Mitigation: helpers take the element and value,
   step 1 decides the wrapper, the import test both ways.
7. **File sizes.** `test_fragments_generated.py` 851 (split first),
   `fragments.py` 519 (shrinks).

Unknown:
- Whether the inventory counts `raise FragmentMergeError(MESSAGE, ...)`
  (a `CodedValueError` subclass) as coded (I: yes, by class; check with a
  fixture at step 1, as PR 14 did for `build_error`).
- Every exception class the 3.0.1 deserialiser raises (I: `KeyError`,
  `TypeError`, `ValueError`, `AttributeError`); the `spdx` stage catches
  `Exception` after the re-raises, so an unknown one still lands there.
- Whether a fragment can ever reach F4 under `loom merge` (I: no; the
  merged document's id hashes the file names).
- `docs/message-codes-fragments.md`'s size (I: about 15 KB).
- Whether `project_document_id` raises anything uncoded today (Q9's
  probe settles it).

## 11. Step 1 result (2026-11-23, Opus)

Built in the worktree, uncommitted. Families as plan 4.2 (all ten, topic
`fragments`, "SBOM fragments", `since` 0.25.0); page 18,886 B, 301 lines.

**Final lines** (`messages/_fragments.py`, `_fragments_merge.py`). A
fragment line ends `; not merged` or, required,
`; required, so the merge will fail` (`NOT_MERGED`, `MERGE_WILL_FAIL`,
built by `fragment_lines(text)`), so each twin differs only in its outcome:
- `fragment-unreadable`: `FILE=<file>: SBOM fragment could not be read (<failure>); ...`
- `fragment-invalid`: `... SBOM fragment is not valid JSON (<failure>); ...`
  and `... is not SPDX 3 JSON-LD Pitloom can merge (<failure>); ...`
- `fragment-unusable`: `... SBOM fragment is the document being merged into (<spdx-id>); ...`
- `input-not-found/fragment` (Q6): `FILE=<file>: SBOM fragment not found; ...`
  (subject `FILE`; `did` names `fragment-missing`)
- `fragment-missing` E: `<number> required SBOM fragment(s) not merged: <files>; fix each as its WARNING says`
  and **Q1**: `no SBOM fragment in '<path>' could be merged; fix each as its WARNING says`
- `fragment-digest-invalid`: `FILE=<file>: SHA-256 <sha256> does not match the configured <declared>`
- `reference-not-found` W: `Merge: ELEMENT=<spdx-id>: <property> names <reference>, which is not in the merged document; regenerate the base SBOM, then run the enrichment again`;
  E: `<number> reference(s) to elements not in the merged document; regenerate ...`
- `fragment-conflict`: `Merge: ELEMENT=<spdx-id>: <property> differs; kept <kept>, dropped <dropped>`;
  `... <property> key <entry-key> differs; kept ..., dropped ...`
- `fragment-id-conflict`: `Merge: ELEMENT=<spdx-id>: id held by a '<holder-type>', also wanted by a '<type>'; both kept, the later is now <new-id>`;
  `... id held by two '<type>' elements of different <algorithm> digests; both kept, the later is now <new-id>`
- `fragment-hash-conflict`: `Merge: ELEMENT=<spdx-id>: a '<type>' named <name> has SHA-256 <digest>, another of that name <other-digest>; both kept`
- `generated-value-conflict` (INFO): `... <property> generated from the model file replaced by a fragment's; kept ..., dropped ...`;
  `... name replaced by the one the fragments agree on; kept ..., dropped ...`;
  `... <property> now holds a value; dropped its not_measured provenance of <provenance-field>`
- Summaries (texts unchanged): `MERGE_MERGED`, `FRAGMENT_VALIDATE_VALID`,
  `FRAGMENT_LIST_NONE`, `ENRICH_REGISTER_HINT`.

**Q1 variant**: a second ERROR line of `fragment-missing` itself (no
`/variant`): the condition (a merge without the fragments it needed), the
effect and the advice (each fragment's WARNING says why) are the same.
Zero fragments given is unreachable there: `generate_merged_sbom` and the
CLI raise `input-not-found` (`no JSON fragment file in`) first. A file
holding `[]` reads as an empty fragment and counts as merged.

**Exports for agent A** (`pitloom.messages.fragments`):
- `FragmentReadError(stage, cause)`, `.stage` in `READ_STAGES`, `.cause`;
  `str()` is the masked `failure` text.
- `warn_fragment_unread(log, file, exc, *, required)`,
  `warn_same_document(log, file, spdx_id, *, required)`.
- `warn_property_conflict(log, *, spdx_id, prop, kept, dropped, key=None)` (U1, U2 with `key`).
- `warn_id_conflict(log, *, spdx_id, element_type, holder_type, new_id, hash_algorithm)` (U3; `None` = other type).
- `warn_hash_conflict(log, *, spdx_id, element_type, name, digest, other_digest)` (U4).
- `say_generated_value_replaced(log, *, spdx_id, prop, kept, dropped)` (G1),
  `say_model_name_replaced(log, *, spdx_id, kept, dropped)` (G2),
  `say_not_measured_dropped(log, *, spdx_id, prop, provenance_field)` (G3).
- `kept`/`dropped`: a `str` (quoted) or `DescribedValue(describe_value(v))`
  for anything else; any other type raises `InternalError`. `prop` takes
  the binding name (`from_`); the line writes the JSON-LD name.
- `DIGEST_MISMATCH_LINE`/`FRAGMENT_DIGEST_INVALID` (L5: `emit(..., file=, measured=, declared=)`),
  the four summaries (`say_summary`), `MERGE_PREFIX`.
- Reader (`assemble/spdx3/_fragments_read.py`): `read_fragment_bytes(path)`
  (stage `read`), `parse_fragment(raw, *, file) -> ParsedFragment(data,
  objects)` (stages `json`, `spdx`), `read_fragment_set(path, *, file=None)`.
  Q10: `fragment list` reads the bytes once, hashes them, then parses.
- `generate_merged_sbom(..., on_merged: Callable[[int], None] | None = None)`:
  called with the merged count after the SBOM is written (M1, Q2).

**Changed from the plan, and why**:
- Field names cannot hold digits (`%\(([a-z_]+)\)s`): `sha256`/`other_sha256`
  became `digest`/`other_digest`, both `excerpt` (quoted, cut at 120):
  a fragment's digest is attacker text, so `measured` (strict hex) would
  raise. New fields also `entry_key` (a dictionary key, cut: `entry` is not)
  and `hash_algorithm`.
- `MERGE_PREFIX` lives in `_fragments.py` (F1 uses it; `_fragments_merge`
  imports `_fragments`).
- Value wrapper: `DescribedValue(str)` in `_field_writers.py`; `kept` and
  `dropped` (`_fields_lock.excerpt_text`) write it on one line, masked and
  cut, unquoted.
- `FragmentReadError` is defined in `pitloom.messages` (as
  `BuildFailedError`), so the catalogue needs no `assemble` import.
- `FragmentLicenseRangeError` now subclasses `FragmentMergeError` only
  (both bases would be an MRO error once `FragmentMergeError` is a
  `CodedValueError`); `isinstance` checks are unchanged.
- The lone-surrogate WARNING is said after a successful parse only (a
  fragment left out says one line, not two).
- A fragment is named as configured (`frag.path`); with
  `adopt_fragment_roots` (`loom merge`) as the directory the caller passed
  (`given_spelling`, a `TypedPath` keeps the user's) joined with its name.
  The CLI resolves the directory today, so agent A passes
  `args.fragments_dir` (or `keep_spelling`) to show what the user typed.
- `_fragment_read_failure_message` and `_same_document_message` are kept
  (commented) until `cli/commands/fragment.py` stops importing them; the
  integrator removes both with their `__all__` entries and
  `tests/test_messages_quote_paths.py:72-73`.

**Q9 probe (blocker for L7 as ruled)**: `project_document_id` over PR 12's
corpus plus extras: every failure is coded, but five have no `WARNING`
twin, so `relay_coded_warning` raises `InternalError`: `metadata-invalid`
(`has a number over <n> digits`, an invalid `name`), `project-name-missing`
(setup.cfg), `project-not-found` and `config-invalid`. The last two are
unreachable from `fragment list` (it read the same configuration first);
the first three are reachable. Needs a ruling: add WARNING twins to those
lines (and their `did`), or Q9's alternative.

**Q9 ruled (coordinator, 2026-11-23): WARNING twins added** (R6, PR 12 Q3
precedent), in `messages/_metadata_read.py` through `warning_twins`, each
the ERROR line's template at `WARNING`:
- `metadata-invalid`: `FILE=<file>: not valid [project] metadata; <failure>`
  (an invalid name lands here) and `FILE=<file>: <field> has a number over <number> digits`.
- `project-name-missing`: `DIR=<dir>: no project name in setup.cfg [metadata] or a literal setup(name=...)`,
  `FILE=<file>: [metadata] has no project name`,
  `FILE=<file>: no project name: setup(name=...) is not a string literal`.
- Each `did` now says `loom fragment list` reports them as a WARNING and
  lists with `SAME_DOCUMENT=-`. The metadata page is 17,181 B, 263 lines.
- `project-not-found` and `config-invalid` keep no twin: `fragment list`
  reads `[tool.pitloom]` from `pyproject.toml` first and stops (or lists
  nothing) before the id is asked for. A relay of either still raises
  `InternalError` (`tests/messages/test_metadata_fragment_relay.py`, which
  also relays the ten reachable corpus errors with a trusted code).
- `tests/messages/test_metadata_relays.py` and `test_metadata_say_edges.py`
  now use `project-not-found` as their twinless coded example.

L7 call shape for agent A (`cli/commands/fragment.py`, `_own_document_id`):

```python
from pitloom.core.internal_error import InternalError
from pitloom.messages.metadata import relay_coded_warning

try:
    return project_document_id(project_dir)
except (InternalError, MemoryError):
    raise
# pylint: disable-next=broad-exception-caught
except Exception as exc:
    relay_coded_warning(log, exc, quiet=False)  # InternalError when uncoded
    return None
```

**E1 restored, coded (coordinator ruling 2026-11-23)**: E1 is reachable after
all: a fragment with an empty `@graph`, or a file holding `[]`, merges and
states no creation time. New family `datetime-missing` (topic `fragments`,
WARNING, condition `missing`, effect weaker, actor user, since 0.25.0):
`Merge: no fragment states a creation time; created set to <datetime>`
(new field `datetime`: an aware datetime written `YYYY-MM-DDTHH:MM:SSZ`).
Said by `finish_merge_document` (`_fragments_envelope.py`) through `emit`.
Its advice names SOURCE_DATE_EPOCH, not `--creation-datetime`: `loom merge`
has no such option. Tests: `test_generators_merge.py::test_no_creation_time_anywhere_is_the_epoch_start`
pins the code again; `test_fragments.py` holds the A-and-B case (no created
and no SOURCE_DATE_EPOCH: 1970 and one line; either present: silent).
The two old text builders are removed from `fragments.py` (nothing imports
them any more), with their `_QUOTING_CALLS` entries.
