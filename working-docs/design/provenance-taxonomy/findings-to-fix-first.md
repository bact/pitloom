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

### Groundwork the code stage needs, with no change of output

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-1 | **Provenance segments built by hand.** About 75 f-strings and suffix constants write ` \| Field: ...` or ` \| Method: ...` without `provenance_segment`, most in `extract/ai_model/`; the rule and its lint test say every string goes through the builders. To check with it: whether any value put into such a segment comes from a file (a `\|` in it would forge a segment) | read on `main` dd31412b, 2026-11-23 (a search; the values were not traced) | no |
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
| PIT-20 | **Four Hub loopback tests fail now and then on a socket the Hub library leaves open.** `tests/extract/remote/test_hub_loopback.py`, on "Test on Python 3.13 (macos-latest)": `ResourceWarning: unclosed <socket.socket ...>` raised at `huggingface_hub/utils/_detect_agent.py`, turned into a failure by `filterwarnings = error`; 4 failed, 18,604 passed. The same workflow passed on another pull request five minutes before, so it hangs on when Python reports the socket. A fix on `main`: a narrow, module-qualified `ignore` for that warning, or the library's agent detection switched off in tests. A rerun does not show it gone | CI of pull request 519 (a change of documents only), run 45168805298, 2026-11-23; the library's version was not found in the log | no |

### To look into, no fix known

| # | Question | What is known |
| --- | --- | --- |
| PIT-15 | Why the Hub's parameter total and Pitloom's own sum differ | in 15 of 128 repositories (benchmark, 2026-11-12); the cause was not looked for |
| PIT-16 | Whether a Magika package version fixes its model | `Tool: magika==x` is written as if it did; no code reads the model's version |
| PIT-17 | Whether a card's `model-index` is read | two examples are marked "to check" ([examples/originator.md](examples/originator.md), OD-11; [examples/other-party.md](examples/other-party.md), PT-9) |
| PIT-18 | Whether the licence conflict of the main package still writes no warning | read at the base; `main` has a `license-conflict` message for another case |
| PIT-19 | The order in which setuptools merges `setup.py` and `setup.cfg` | taken from the code (#287), not read again |

## What is not here

The work the taxonomy itself asks for (keys, labels, the licence
relationships, schema versions): hazards 4 to 15 of
[renames-and-migration.md](renames-and-migration.md). PIT-1 to PIT-3
are its hazards 3, 2 and 1, listed here because they change no output
and can go before it.
