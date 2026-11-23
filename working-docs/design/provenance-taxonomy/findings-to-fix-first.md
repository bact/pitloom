---
Created: 2026-11-23
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Findings to fix first: LicenseID and Pitloom

See also: [README.md](README.md) (the claim model),
[asserter-licence.md](asserter-licence.md) (the gate for a text match and
its measurement), [source.md](source.md) (a source that can change),
[renames-and-migration.md](renames-and-migration.md) (hazards for the
code stage, the sweep against `main`).

**Status:** list, written 2026-11-23. The taxonomies are agreed (stage
(c)); the code stage waits for the 0.25.0 cut and for the fixes here
(the user, 2026-11-23). These are things the taxonomy work came across
that a fix in LicenseID or in Pitloom would help, whatever the taxonomy
says. A change that only the new vocabulary asks for is not here: it is
in the hazards list.

## How to read an entry

- **Seen** says how the finding is known: *run* (a command run on the
  day given), *read* (in the code, with the revision), or *measured* (a
  count over a set of files, with its day and version).
- **On `main`** says whether a page on `main` (dd31412b) already names
  it; "no" means none was found by a search of `known-bugs`, the
  roadmap and the LicenseID handoff page, not that none exists.
- LicenseID is not edited from here. Its entries end in a prompt to
  hand over; its table has no **Seen** column, since one sentence
  above it holds for every row.

## LicenseID

Every row was run on 2026-11-23 with LicenseID 0.9.0 and 0.9.1 (SPDX
License List 3.29.0, as packaged), by `detect --top 2 -v` on a licence
file of a wheel from PyPI; the two versions give the same output. A
count "of 197" is from the measurement of 2026-11-19 on 0.9.0
([asserter-licence.md](asserter-licence.md)) and was not run again.

| # | Finding | On `main` |
| --- | --- | --- |
| LID-1 | **An optional part of a listed text is matched as if required: a wrong id first.** An Apache 2.0 text without its appendix gives `Pixar` (0.9963), then `Apache-2.0` (0.9921): bandit 1.9.4. Nine of 197 files | yes: the handoff page (`Pixar` over `Apache-2.0`, from #286, open) |
| LID-2 | **The same cause: no result at all.** The LGPL version 3 text alone (fickling 0.1.12; 1,234 words, the text FSF ships as `COPYING.LESSER`) gets an empty result. With `--threshold 0` the first of twelve is `copyleft-next-0.3.0` at 0.6384, and no LGPL id is among them. The indexed text of `LGPL-3.0-only` has 6,888 words: the LGPL part and the whole GPL version 3 text (5,644 words in a plain copy) | no |
| LID-3 | **An empty result gives no reason.** For LID-2, and for pydantic in LID-4, `--json` prints every field as `null`; `resolve` has a `reason` in the like case | no |
| LID-4 | **A title line and a copyright line hide the licence.** Four plain MIT texts: attrs 26.1.0 gives `MIT-advertising` (0.8724), pytest 9.1.1 `FSL-1.1-MIT` (0.9151), PyYAML 6.0.3 `Xnet` (0.9023), and pydantic 2.14.3 an empty result. The first, second and fourth begin "The MIT License (MIT)" and a copyright line; PyYAML has no title and two copyright lines. tomli 2.5.0 begins "MIT License" and gives `MIT` at 1.0. In 21 of 197 files Pitloom's second reading (the text without its copyright lines) names another id than LicenseID's first. Only the first three lines of each file were read here | partly: the handoff page (PyYAML gives `Xnet`); the empty result is new |
| LID-5 | **A file with several licence texts gets one id, and nothing says there are more.** mypy 2.4.1 (the MIT text, then the Python licences: `Python-2.0.1`, 0.9203), NumPy 2.2.6 (its BSD text and bundled licences: `LGPL-2.1-or-later`, 0.9472), python-dateutil 3.0.0 (an Apache notice, then the BSD text that applies to all code: `Apache-2.0`, 0.9187), PyMdown Extensions 12.3 (`MIT`, 0.9342) | no |
| LID-6 | **One text, two ids, both `exact`.** The MPL 2.0 text of pathspec 1.1.1 is exact at 1.0 for `MPL-2.0` and for `MPL-2.0-no-copyleft-exception`; no field says the text is shared (`variant_stated` is for `-only` and `-or-later`) | partly: the handoff page asks it for URLs that map to several ids |
| LID-7 | **A notice scores as the text.** CacheControl 0.14.4 (13 lines that name Apache 2.0): `Apache-2.0`, `method` `text`, score 1.0, coverage 0.0571. Nothing but the coverage tells a notice from the licence | no |
| LID-8 | **`score` reads as a measure of fit and is a ranking key.** `Pixar` at 0.9963 is wrong, a 13-line notice has 1.0. A caller that sets a threshold on it is misled | no |
| LID-9 | **`coverage` goes above 1, and no page says what it measures.** NumPy 2.2.6: 1.7164 for the first result and 34.5321 for `BSD-3-Clause`; mypy 2.4.1: 1.2882; PyMdown Extensions 12.3: 3.6882 | no |

What would help Pitloom most, in order: LID-1, LID-2 and LID-4 (the
SPDX matching guidelines let optional text be absent and a title or a
copyright notice differ), then LID-3, LID-5 (a sign that more than one
text was found), LID-7 (a sign that the input is a notice), LID-6,
LID-8 and LID-9 (the documentation). With the first three fixed,
Pitloom's second reading and most of its gate
([asserter-licence.md](asserter-licence.md)) could go.

### Prompt for LicenseID (written 2026-11-23)

The letters are the prompt's own: A1 is LID-1, A2 is LID-2, A3 is
LID-4, B1 to B4 are LID-3, LID-5, LID-7 and LID-6, B5 is LID-8 with
LID-9.

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

Not read for this page: the list's XML for the optional marks (LID-1,
LID-2), and the full text of the four MIT files of LID-4.

## Pitloom

Read at the draft's base 257b7260 unless a row says `main`. Each needs a
second look on `main` before work starts: 135 commits lie between.
Read again on `main` dd31412b on 2026-11-23, for the prompt at the end
of this section: PIT-1, PIT-2 (one of its five sites), PIT-3, PIT-4,
PIT-7, PIT-8, PIT-9 and PIT-12. The prompt gives the file and line of
each, and marks every other item as read at the base or to check.

### Groundwork the code stage needs, with no change of output

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-1 | **Provenance segments built by hand.** About 75 f-strings and suffix constants write ` \| Field: ...` or ` \| Method: ...` without `provenance_segment`, most in `extract/ai_model/`. The lint test (`tests/test_provenance_builders_lint.py`) allows it: it is strict for every key but `Field:` and `Method:`, and for those two it refuses only an interpolated name that looks external (`entry`, `path`, `url`, `name` and the like). So no test shows that a value put into such a segment holds no `\|` (one would forge a segment). Three interpolations were traced (Safetensors, CRFsuite): each comes from a fixed list. To do: trace the rest, send all through the builders, then make the test strict for the two keys | read on `main` dd31412b, 2026-11-23: the lint test in full; three values traced, the rest not | no |
| PIT-2 | **Provenance strings used as data.** Five sites compare or parse one again (`_setuptools_options.py`, `_optional_dependencies.py`, `_setuptools_dynamic.py`, `lock/cascade.py`, `scanner.py`). A change of wording changes behaviour. Carry a typed value beside the string | read at the base | no |
| PIT-3 | **The document id hangs on a provenance string.** The provenance of `locked_dependencies` is hashed into the document UUID, so a reworded label changes every SPDX id of such a document. Seed it by a function of its own that keeps today's text | read at the base; still passed to the document model on `main` | no |

### Readers and output

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-4 | **A Git URL leaves no trace of the commit.** The checkout resolves the commit; `loom project` on a URL gave an SBOM with no commit, no ref name and no host | run at the base with the fetch stood in for; on `main` no reader of the commit was found in `extract/remote`, `assemble`, `_generators.py`, `__main__.py` | no |
| PIT-5 | **Hub files can be read at no state.** When `model_info` fails or states no `sha`, the card, the config files and the licence files are read with no revision (one `WARNING:` each), so they may come from different commits. (The list of licence files is fixed on `main`: it comes from the same answer.) | read at the base; on `main` only the list of licence files was read again | no |
| PIT-6 | **A dependency with no version takes the latest release's licence and originator, and the claim names no release.** | read at the base | no |
| PIT-7 | **`last_modified` of the Hub is written as the release time of the revision.** The Hub documents it as the date of the last commit to the repository, not of a revision | read at the base; the Hub's wording as quoted in [source.md](source.md) | no |
| PIT-8 | **`embed-wheel --project-dir` trusts the directory.** Nothing compares its name and version with the wheel's, and its authors are taken already. Warn on a mismatch | read at the base (three embed modules) | no |
| PIT-9 | **A licence value with no source at all is written as a concluded licence.** It should not reach the SBOM as one; find the reader that drops the source | read at the base | no |
| PIT-10 | **A model over the header cap gives an error and no field** (a 10 GB GGUF whose header read stops at 64 MiB: `ModelOverCap`). By the evidence rule a cap bounds reading, not reporting: the file's size, at least, is known. Whether a parameter count over the cap writes `over-cap` was not checked | from the benchmark's probe, release 0.2 | no |
| PIT-11 | **Three provenance gaps at readers.** The wheel reader records none for `description`, `requires_python`, `urls` (the sdist reader does); Hub licence detection writes no `Tool` (in-package detection does); ONNX `type_of_model` has no entry | read at the base | no |
| PIT-12 | **No `completeness` on any relationship.** One `contains` per child; the one function that could give completeness returns none | read at the base, 2026-11-23 | no |
| PIT-13 | **`simplelicensing_licenseListVersion` is not set.** | read at the base | yes: `known-bugs/licences-and-licenseid.md`, the roadmap |
| PIT-14 | **The page on licence provenance says PEP 639 forbids an SPDX `license` beside licence classifiers.** The `pyproject.toml` specification says a build tool may raise an error | `docs/metadata-provenance-licences.md` on `main`; the specification's source read 2026-11-23 | no |

### Tests and CI

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-20 | **Fixed 2026-11-23 (pull request: to fill in). Four Hub loopback tests failed now and then on an unclosed socket.** `tests/extract/remote/test_hub_loopback.py`, macOS, Python 3.13: `ResourceWarning: unclosed <socket.socket ...>` at `huggingface_hub/utils/_detect_agent.py`, a failure by `filterwarnings = error`; the rerun failed the same way on Windows. Cause: on its first agent detection in a process, `huggingface_hub` (2.4.0 in that run) asks the real Hub (`constants.ENDPOINT`) for a registry; the loopback guard of `tests/conftest.py` refused that `connect` with a `RuntimeError`, and `socket.create_connection` closes its socket on an `OSError` only. Seen only when a worker's first detection falls in a `loopback` test. Fix: the guard closes the socket it refuses; no warning filter, no library switch. The patch of the library's private `_fetch_registry` from pull request 524 covered one file of two and is removed. Regression test: `test_a_refused_connection_leaves_no_open_socket` | CI of pull request 519, run 45168805298, both attempts; run on demand 2026-11-23, the registry reset before each test: 19 tests failed before the fix, none after (Python 3.10 with 2.2.0, 3.13 with 2.4.0) | no |

### To look into, no fix known

| # | Question | What is known |
| --- | --- | --- |
| PIT-15 | Why the Hub's parameter total and Pitloom's own sum differ | in 15 of 128 repositories (benchmark, 2026-11-12); the cause was not looked for |
| PIT-16 | Whether a Magika package version fixes its model | `Tool: magika==x` is written as if it did; no code reads the model's version |
| PIT-17 | Whether a card's `model-index` is read | two examples are marked "to check" ([examples/originator.md](examples/originator.md), OD-11; [examples/other-party.md](examples/other-party.md), PT-9) |
| PIT-18 | Whether the licence conflict of the main package still writes no warning | read at the base; `main` has a `license-conflict` message for another case |
| PIT-19 | The order in which setuptools merges `setup.py` and `setup.cfg` | taken from the code (#287), not read again |

### Prompt for the Pitloom fixes (written 2026-11-23)

The prompt orders the work in five pull requests. Ruled by the user on
2026-11-23 (the recommendations taken as put):

- **When.** PIT-20 goes now; the other fixes start after the 0.25.0 cut
  and go into the release after it.
- **PIT-8.** A directory whose name or version differs from the wheel's
  gets a `WARNING:`; the run goes on (not refused).
- **PIT-4.** The commit goes into the package's download location, as a
  URL of the repository with the commit, and into a provenance entry.
  Not read for this ruling: what `main` writes there today for a Git
  URL target, and the form SPDX 3 expects.
- **PIT-9, PIT-12.** No ruling yet: each has a default in the prompt
  (never a concluded licence, and dropped with a `WARNING:` until the
  origin is known; `complete` only where the source lists the whole
  set), to confirm or change once the facts are in. Taking the two
  defaults in with "the recommendations" is this page's reading.

```text
Handoff: Pitloom fixes to land before the provenance-taxonomy code stage

Context
- Source page: working-docs/design/provenance-taxonomy/
  findings-to-fix-first.md (on main). Ids PIT-n below are that page's.
- The taxonomy redesign (same folder, README.md) is agreed as a design
  and NOT built. Do not start it: no new provenance keys, labels,
  licence relationships or schema versions here. These fixes only clear
  the ground.
- Line numbers are from main at dd31412b (2026-11-23). Main has moved:
  find each place again by symbol before editing.
- Evidence level per item:
  [main]  read on main dd31412b
  [base]  read at 257b7260 only (135 commits older): confirm first
  [check] not confirmed: reproduce before any fix
- If an item no longer reproduces on main, say so and skip it.

Rules
- Fresh worktree from current main; one PR per group below; the user
  decides every merge. Ruled 2026-11-23: PR 1 goes now; PR 2 to PR 5
  start after the 0.25.0 cut and go into the release after it.
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

PR 2. Groundwork: zero change of output
Proof for the whole PR: SBOM, stderr and --json diff against main empty
on the manual CLI checks and the parity/determinism harness.

PIT-1 [main]. About 75 f-strings and suffix constants write
  ` | Field: ...` or ` | Method: ...` without provenance_segment, most
  in src/pitloom/extract/ai_model/.
  The lint does not forbid this.
  tests/test_provenance_builders_lint.py has R1 (strict, every key but
  Field:/Method:), R2 (heuristic: a Field:/Method: string interpolates
  no name matching entry|prefix|member|label|path|raw|url|archive|name)
  and R3 (" | ".join). So these sites pass by design.
  Traced: three interpolations (safetensors `found[0]`, crfsuite
  `location`), all from fixed lists; no forged segment found. The rest
  are not traced.
  Do: trace every interpolated value to its origin; route all sites
  through the builders; then make the lint strict for Field:/Method:
  too. Check first that the builder gives byte-identical text for each
  site (escaping of `|`); where it does not, stop and report.

PIT-2 [main for one site, base for four]. Provenance strings used as
  data. Confirmed: src/pitloom/extract/project/_setuptools_options.py
  :456 `py_wins = metadata.provenance.get("license") == py_licence[1]`.
  Named at the base, not found again by a search on main:
  _optional_dependencies.py, _setuptools_dynamic.py, lock/cascade.py,
  scanner.py. Find them (comparisons, startswith, split, `in` on a
  provenance value).
  Do: carry a typed value beside the string (which source won), compare
  that. Test per site: reword the provenance text in the test, behaviour
  unchanged.

PIT-3 [main]. src/pitloom/core/models.py:190-197 adds
  "\x00" + locked_dependencies_provenance to the document UUID seed;
  the default text is `_DEFAULT_LOCKED_PROVENANCE = "Source: lock file |
  Method: resolved_lockfile"` at assemble/spdx3/deps_installed.py:74.
  A reworded label would change every SPDX id of such a document.
  Do: a seed function of its own that returns today's exact text for
  each case, frozen and commented as an id input. Test: pin the UUID of
  a fixture for each provenance variant; a second test rewords the
  label and asserts the same ids.

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

## What is not here

The work the taxonomy itself asks for (keys, labels, the licence
relationships, schema versions): hazards 4 to 15 of
[renames-and-migration.md](renames-and-migration.md). PIT-1 to PIT-3
are its hazards 3, 2 and 1, listed here because they change no output
and can go before it.
