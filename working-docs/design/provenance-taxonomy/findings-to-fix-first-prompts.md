---
Created: 2026-11-27
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Findings to fix first: the hand-over prompts

See also: [findings-to-fix-first.md](findings-to-fix-first.md) (the
findings, LID-1 to LID-9 and PIT-1 to PIT-21, and the rulings on the
Pitloom fixes).

## Prompt for LicenseID (written 2026-11-23)

The letters are the prompt's own: A1 is LID-1, A2 is LID-2, A3 is
LID-4, B1 to B4 are LID-3, LID-5, LID-7 and LID-6, B5 is LID-8 with
LID-9. LicenseID 0.9.2 answers A1, A2, A3, B1 (the reason) and B4;
B2, B3 and B5 are still to hand over.

```text
Handoff from Pitloom to LicenseID: text matching findings

Context
- Pitloom reads licence files with `licenseid detect` and declares the
  matched id as the package's licence. A wrong first result becomes a
  wrong declared licence in an SBOM.
- Everything below was run on 2026-11-23 with LicenseID 0.9.0 and 0.9.1,
  SPDX License List 3.29.0 as packaged
  (`licenseid --db <new file> update --source packaged`). Both versions
  give the same output on every input.
- Command used: `licenseid --db <db> detect --top 2 -v <file>`.
- Inputs are licence files of wheels on PyPI, named as
  <project> <version>: <path inside the wheel's .dist-info>.
- Do not touch Pitloom. Do not change results silently: a changelog line
  for every result that changes for existing input.

A. SPDX matching guidelines not applied to the input
The guidelines let optional text be absent and let a title and a
copyright notice differ. These inputs fail on exactly those points.

A1. Optional text missing: wrong id first.
    bandit 1.9.4: licenses/LICENSE (Apache 2.0, no appendix)
    -> Pixar 0.9963 (similarity 0.9913), then Apache-2.0 0.9921
       (similarity 0.9421, coverage 0.8859).
    The indexed Apache-2.0 text holds the appendix; Pixar's has none.
    Expected: Apache-2.0 first. Seen in 9 of 197 licence files of one
    environment (0.9.0).

A2. Optional text missing: no result at all.
    fickling 0.1.12: licenses/LICENSE (the LGPL version 3 text alone,
    1,234 words, as FSF ships COPYING.LESSER)
    -> empty result. With `--threshold 0 --top 12` the first is
       copyleft-next-0.3.0 at 0.6384 and no LGPL id is listed.
    The indexed text of LGPL-3.0-only has 6,888 words: the LGPL part
    plus the whole GPL version 3 text (5,644 words in a plain copy).
    Check whether the list's XML marks that part optional.
    Expected: LGPL-3.0-only (or -or-later, with variant_stated false).

A3. Title line and copyright line: wrong id, or none.
    All four are plain MIT texts.
    attrs 26.1.0: licenses/LICENSE     -> MIT-advertising 0.8724
    pytest 9.1.1: licenses/LICENSE     -> FSL-1.1-MIT 0.9151, then
                                          MIT-advertising 0.8662
    pydantic 2.14.3: licenses/LICENSE  -> empty result
    pyyaml 6.0.3: licenses/LICENSE     -> Xnet 0.9023
    The first three begin "The MIT License (MIT)" and one copyright
    line; pyyaml has no title and two copyright lines.
    Control: tomli 2.5.0: licenses/LICENSE begins "MIT License" and one
    copyright line -> MIT 1.0000, then JSON 0.9954. Correct.
    Expected: MIT for all four.
    Pitloom works around this with a second detect call on the text
    without its copyright lines; in 21 of 197 files that second reading
    names another id than the first.

B. Results that need a signal

B1. An empty result has no reason. For A2 and for pydantic in A3,
    `detect --json` prints every field as null. `resolve` gives a
    reason in the like case. Ask: a reason, and the nearest candidate.

B2. Several licence texts in one file: one id, no sign of the others.
    mypy 2.4.1: licenses/LICENSE (MIT, then the Python licences)
      -> Python-2.0.1 0.9203
    numpy 2.2.6: LICENSE.txt (its BSD text, then bundled licences)
      -> LGPL-2.1-or-later 0.9472, then BSD-3-Clause 0.9319
    python-dateutil 3.0.0: licenses/LICENSE (a short Apache notice,
      then the full BSD three-clause text that the file says applies
      to all code) -> Apache-2.0 0.9187 (coverage 0.2639)
    pymdown-extensions 12.3: licenses/LICENSE.md -> MIT 0.9342
    Ask: a flag or a list that says more than one text was found.

B3. A notice scores as the full text.
    cachecontrol 0.14.4: licenses/LICENSE.txt (13 lines naming
    Apache 2.0) -> Apache-2.0, method text, score 1.0000,
    coverage 0.0571.
    Ask: a way to tell a notice or a pointer from the licence text
    (another method value, or a documented field to test).

B4. One text, two ids, both exact.
    pathspec 1.1.1: licenses/LICENSE (MPL 2.0)
    -> MPL-2.0 exact 1.0000 and MPL-2.0-no-copyleft-exception exact
       1.0000. No field says the two ids share one text
       (variant_stated covers -only and -or-later).
    Ask: a field for a shared text, as asked before for URLs that map
    to several ids.

B5. `score` and `coverage` are not what their names suggest.
    score: Pixar 0.9963 is wrong (A1), a 13-line notice has 1.0000 (B3).
    coverage: above 1 in B2 (numpy: 1.7164, and 34.5321 for
    BSD-3-Clause; mypy: 1.2882; pymdown-extensions: 3.6882).
    Ask: say in the documentation what each field measures and its
    range, and that score ranks and does not measure fit; or add a
    field a caller can set a threshold on.

Priority for Pitloom: A1, A2, A3, then B1, B2, B3, B4, B5.
With A fixed, Pitloom can drop its second reading and most of its own
gate (score 0.85 or more, no other family within 0.01).

Already asked before and still open on 0.9.1: Pixar over Apache-2.0
(A1) and a leading copyright notice hiding MIT (A3, pyyaml).

Deliver
For each item: reproduce, fix or document, add a test with a minimal
text sample, add a changelog line. Report which items you did, which
you refused and why, any new or changed field of the detect result,
and the release that holds it.
```

## Prompt for the Pitloom fixes (written 2026-11-23)

Rulings: [findings-to-fix-first.md](findings-to-fix-first.md#rulings-on-the-pitloom-fixes-2026-11-23).

```text
Handoff: Pitloom fixes to land before the provenance-taxonomy code stage

Context
- Source page: working-docs/design/provenance-taxonomy/
  findings-to-fix-first.md (on main). Ids PIT-n below are that page's.
- The taxonomy redesign (same folder, README.md) is agreed as a design
  and NOT built. Do not start it: no new provenance keys, labels,
  licence relationships or schema versions here. These fixes only clear
  the ground.
- PR 2 below was written again on 2026-11-28 for main 88ad620e (release
  0.25.1): its line numbers were read there. PR 3 to PR 5 are still as
  written on 2026-11-23 for dd31412b; the table "Third look on main" of
  the source page says what moved, so read it first and find each place
  again by symbol.
- Evidence level per item:
  [main]  read on main dd31412b
  [base]  read at 257b7260 only (135 commits older): confirm first
  [check] not confirmed: reproduce before any fix
- If an item no longer reproduces on main, say so and skip it.

Rules
- Fresh worktree from current main; one PR per group below; the user
  decides every merge. Ruled 2026-11-23: PR 1 goes now; PR 2 to PR 5
  start after the 0.25.0 cut. Releases 0.25.0 and 0.25.1 are out: each
  PR starts on the user's word.
- Every fix: a regression test that fails on the base tree. Gates A and
  B of AGENTS.md. Messages go through pitloom.messages (catalogue,
  generated reference and any SKILL.md that quotes them, in one change).
- An item marked "ruling" needs the user's answer before code: put the
  options with a recommendation, do not pick. An item marked "default"
  has an answer to work from: come back only if the facts speak
  against it.
- Agents (the user, 2026-11-23): a cheaper model and lower effort for
  simple, mechanical steps (searches, lint and test runs, a traced
  value); the strongest model and higher effort for planning, complex
  changes and any question with no answer known in advance. Run a
  linter yourself before trusting a cheap agent's "pass".
- Never edit LicenseID. PIT-13 is tracked elsewhere: leave it.

PR 1. CI flake -- DONE 2026-11-23, skip it: the PIT-20 row has the
  cause and the fix (neither fix shape below was used).
PIT-20 [main, CI log]. tests/extract/remote/test_hub_loopback.py: 4
  tests failed on "Test on Python 3.13 (macos-latest)" with
  `ResourceWarning: unclosed socket.socket` raised at
  huggingface_hub/utils/_detect_agent.py (line 204 in that run), made a
  failure by filterwarnings = error. Seen on run 45168805298 of a
  docs-only PR; the same workflow passed minutes earlier. The library
  version in CI was not found in the log: find it first.
  Fix shapes: (a) switch the library's agent detection off in tests
  (read its source for the supported switch, do not guess an env var);
  (b) a narrow, module-qualified `ignore::ResourceWarning` entry with a
  comment. Prefer (a) if a public switch exists.
  A rerun proves nothing: reproduce by forcing the warning (for example
  gc.collect() after the call with the socket left open), then show the
  fix holds under that.

PR 2. Groundwork: zero change of output (written again 2026-11-28)
Three parts, in this order, each its own PR unless the user says one:
2a (PIT-3) is small and frees every label; 2b (PIT-1) is wide and
mechanical; 2c (PIT-2) needs design per site.
Proof for each part: SBOM, stderr and --json diff against main empty
on the manual CLI checks and the parity/determinism harness, and the
pinned document ids of tests/core/test_models.py unchanged.
Why now: the taxonomy code stage renames provenance keys and values.
Ruled 2026-11-28 (resweep-rulings.md, C10): a released term is never
renamed, so the first release of the new vocabulary must be right, and
nothing may hang on today's wording when it lands.

2a. PIT-3 [main 88ad620e]. The document id hangs on a provenance string.
  core/models.py:192-199, compute_doc_uuid: the seed takes
  "\x00" + locked_dependencies_provenance. Two callers pass it:
  assemble/spdx3/document.py:187 and assemble/_model_generator.py:195
  (project_document_id, used by `loom fragment list`).
  Strings that reach the seed: extract/lock/cascade.py:274-285
  (`Source: <lock> | Method: <method>`, with ` | Note: supersedes
  <lock>` when a lower source loses) and the hand-written
  extract/project/pyproject.py:355-359 (`Source: poetry.lock | Method:
  resolved_lockfile`). `_DEFAULT_LOCKED_PROVENANCE`
  (assemble/spdx3/deps_installed.py:75) does NOT reach it. Not checked:
  a library caller who sets the provenance by hand, and what
  core/project.py merge_project_metadata carries over.
  Done already (pull request 533): tests/core/test_models.py pins 11
  ids by typed strings and two through the real readers (pylock.toml,
  poetry.lock). uv.lock, pdm.lock, Pipfile.lock, requirements.txt and
  the "supersedes" note are pinned by typed strings only.
  Do: (1) one function gives the seed text of a lock source from typed
  facts (which lock, which method, which lock it supersedes), returns
  today's exact text for every case, and is commented as an id input
  that is frozen; both callers use it and no longer read the provenance
  string. (2) Route tests through the real reader for the four locks
  that have none. (3) The test that proves the point: reword a label in
  the provenance (monkeypatch the cascade's text), assert the same ids.
  The existing test
  test_compute_doc_uuid_lock_gate_and_wording_are_id_inputs
  asserts the reverse on the pure function: keep its meaning
  for the function's argument, and say in its name that the argument
  is the seed text, not the provenance.
  Ask first (ruling): a caller-built ProjectMetadata with a provenance
  string of its own -- does its text stay an id input (today), or does
  the seed fall back to the typed facts only?

2b. PIT-1 [main 88ad620e, counted by a scan of the syntax tree].
  Provenance segments built by hand: 62 strings with an interpolated
  value and 4 suffix constants (core/model_originators.py:31,34;
  core/model_parameters.py:42,44); 55 of the 62 are in
  src/pitloom/extract/ai_model/. Beside them 61 whole literals
  (`"Source: x | Field: y"`) with no interpolation. The count did not
  move between 6cb6183f and dfa11c14.
  The lint allows it: tests/test_provenance_builders_lint.py is strict
  (R1) for every key but Field: and Method:, and for those two refuses
  only an interpolated name matching entry|prefix|member|label|path|
  raw|url|archive|name (R2).
  Traced: of 27 values that are not the `Source:` base, 24 come from a
  fixed list or constant, one from a builder, one is a number. Not
  traced: `source` in extract/_core_metadata.py:260 (callers
  _core_metadata.py:289, assemble/spdx3/deps_pypi.py:88), and the
  `source` parameter of extract/ai_model/archive_member.py:61 and
  _pt2_graph.py:116.
  What the builder does (core/provenance.py:223-235, read):
  provenance_segment(base, key, value) appends " | <key>: <value>"
  with the value through sanitize_provenance_text, which writes "|" as
  "/" and escapes control characters and lone surrogates. For a fixed
  ASCII value the text is the same byte for byte.
  Do: (1) finish the trace of the three values above. (2) Route every
  interpolated site and the four suffix constants through
  provenance_segment (a site with two segments chains it). (3) Decide
  with the user whether the 61 whole literals go through the builders
  too (they cannot forge a segment; the gain is one spelling per key
  for the rename). (4) Make the lint strict for Field: and Method: and
  drop R2. Before each site: assert old text == new text for its
  values; where a value could hold "|" or a control character the text
  changes -- stop and report, that is an output change and not this PR.
  Use a cheap agent for the rewrite and the per-site equality check;
  run the linters yourself.

2c. PIT-2 [main 88ad620e]. Provenance strings used as data. Two kinds;
  only the first is this PR.
  Kind A, a string built in this process and parsed or compared again
  in this process (fix: carry a typed value beside the string):
  - extract/project/_setuptools_options.py:456 (the whole string
    compared with ==, decides which side is named first), :225 and
    :307 (parsed for "location" and "source")
  - extract/project/_optional_dependencies.py:60-62
  - extract/project/_setuptools_dynamic.py:288-289
  - extract/lock/cascade.py:240-262 (ranks the lock that was held by
    its parsed source name; shares 2a's typed facts)
  - extract/scanner.py:231 (prefix test to rewrite a copied path, for
    the model and each dataset) and :275 (the same in a warning text)
  - core/evidence.py:223 (reads the Evidence level back to rank)
  - assemble/spdx3/_provenance_encoders.py:49-67 and :87 (the detail
    level `minimal` decides from the parsed string), :70-79 with
    deps_license.py:216 (declared or concluded: `not _source_name`)
  - assemble/spdx3/_license_elements.py:318-326 (_is_noted: compares
    two strings and parses one for normalized-from)
  - assemble/spdx3/deps_installed.py:295 (dedup key on the source
    string of a conflict candidate)
  Kind B, provenance read back from a document someone else may have
  written. These must parse; a typed value cannot reach them. NOT this
  PR (the code stage owns them: renames-and-migration.md, hazards 5 to
  7), but list them in the PR text so the count is whole:
  assemble/spdx3/_fragments_generated.py:61,73;
  _fragments_model_names.py:89-90; _fragments_evidence.py:62,71 (a
  substring test on the spelling `not_measured`);
  export/_spdx3_credentials/_find.py:140 (the schema compared with ==:
  a new schema version stops its reading of notes, silently) and :177;
  scripts/extract_wheel_sbom.py:51,112-125.
  Do, for kind A: plan first, per site, what typed value replaces the
  read-back (an enum or a small frozen dataclass kept beside the
  string; where it lives; who sets it), and show the plan to the user
  before code: this is the one part of PR 2 with no answer known in
  advance, so use the strongest model for it. Then per site a test
  that rewords the provenance text (monkeypatch the builder's output)
  and asserts the behaviour unchanged. A site whose typed value would
  be a new field on a public dataclass: ask first.
  Search again before you start (the list grew at each look):
  parse_provenance_value( call sites (14 at 88ad620e), and ==,
  startswith, `in` on a `.provenance` value.

PR 3. Licence and embed
PIT-9 [main]. assemble/spdx3/_provenance_encoders.py:81-89
  `is_license_concluded` returns `not source or source in
  THIRD_PARTY_SOURCES`: a licence with no source at all is written as
  hasConcludedLicense. Ruling of 2026-11-23: Pitloom alone writes no
  concluded licence.
  Do: first find which reader hands over a licence without a source
  (that is the bug to fix at its origin). Default: the encoder never
  writes a source-less value as concluded; it drops it with a WARNING:
  until the origin is known (not taken so far: declared, or
  InternalError). Run a probe corpus through main and the
  tree and list every relationship that changes.

PIT-8 [main]. `embed-wheel --project-dir`: src/pitloom/embed.py:131
  `_enforce_sbom_name_version` compares a supplied SBOM with the wheel;
  nothing compares the project directory with the wheel, and the
  directory's metadata is taken.
  Do: compare name (PEP 503) and version (PEP 440) of the directory
  with the wheel's; on a mismatch a WARNING: through the catalogue.
  Ruled 2026-11-23: warn only, the run goes on.

PIT-14 [base docs, spec read 2026-11-23]. docs/metadata-provenance-
  licences.md says PEP 639 forbids an SPDX `license` beside licence
  classifiers. The pyproject.toml specification says a build tool MAY
  raise an error. Read the page on main and the specification text,
  then correct the sentence. Docs only.

PR 4. Remote sources: which state was read
PIT-4 [main]. extract/remote/git.py:116 `class GitCheckout` resolves
  the commit; no reader of it outside git.py (searched extract/remote,
  assemble, _generators.py, __main__.py). `loom project` on a Git URL
  gives an SBOM with no commit, ref or host.
  Ruled 2026-11-23: the commit goes into the package's download
  location (a URL of the repository with the commit) and into a
  provenance entry; the taxonomy's Location key is not built. First
  read what main writes there today for a Git URL target and the form
  SPDX 3 expects (neither was read for the ruling); report if either
  speaks against it. Then carry the commit from GitCheckout to the
  assembler; test through the CLI on a local repository.

PIT-5 [base]. When Hub `model_info` fails or states no `sha`, the card,
  config and licence files are read with no revision (one WARNING:
  each) and may come from different commits. On main only the licence
  file list was read again (it now comes from `siblings`).
  Confirm on main. Fix shape: resolve one revision once and pass it to
  every read; if none can be resolved, one message that says the files
  are read at no fixed state.

PIT-7 [main]. extract/remote/huggingface_field.py:371-382 takes
  `hub_info.get("last_modified")` as "the revision's commit time". The
  Hub documents it as the date of the last commit to the repository.
  Nuance: for a read of the default branch head the two are equal; the
  value is wrong only when another revision is read. Read the Hub API
  documentation for a per-revision date before choosing: use that, or
  write the time only when the head was read.

PIT-6 [check]. A dependency with no version takes the latest release's
  licence and originator. extract/remote/pypi.py has RELEASE_UNPINNED*
  messages for it on main. Not checked: whether the provenance of those
  fields names the release that was read. If it does not, add it.

PR 5. Reader gaps
PIT-11 [base]. Three provenance gaps: the wheel reader records none for
  description, requires_python, urls (the sdist reader does); Hub
  licence detection writes no Tool (in-package detection does); ONNX
  type_of_model has no entry. Confirm each on main; fix with the
  sibling's wording, through the builders.

PIT-10 [check]. A model whose header exceeds the read cap raises
  extract/ai_model/limits.py:77 `ModelOverCap` and, as reported, gives
  no field at all (a 10 GB GGUF, header read stopped at 64 MiB). By the
  evidence rule a cap bounds reading, not reporting: file size and
  digest are measurable. Reproduce on main with a synthetic GGUF (main
  has its own header reader since #517, with a partial read marked
  truncated: behaviour may differ now). Not checked either: whether a
  parameter count over the cap writes `over-cap`.

PIT-12 [main]. assemble/spdx3/_document_locked_deps.py:196-209
  `_locked_dependencies_completeness` does `del metadata; return None`;
  no relationship carries completeness.
  Default: `complete` only where the source lists the whole set (a
  lock file read in full?); the rest stay unset. Still a ruling before
  code: propose a table of relationship kinds with evidence; no code
  until answered.

Investigations (report findings, no fix asked)
PIT-15 Hub parameter total differs from Pitloom's own sum (15 of 128
  repositories measured 2026-11-12). Find the cause on three examples.
PIT-16 Does a Magika package version fix its model? `Tool: magika==x`
  is written as if it did.
PIT-17 Is a model card's `model-index` read at all?
PIT-18 Does a licence conflict of the main package still write no
  warning? Main has a `license-conflict` message for another case.
PIT-19 The order in which setuptools merges setup.py and setup.cfg:
  read setuptools' source, do not rely on Pitloom's comment (#287).

Deliver
Per item: confirmed or not on main (with the command or the lines),
what was fixed, the regression test's name, any output that changes
(before and after), what was left and why. For each "ruling" item: the
question, the options, a recommendation. In each PR, mark the row of
findings-to-fix-first.md done with the PR number.
```
