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
  hand over.

## LicenseID

Versions: 0.9.0 and 0.9.1 give the same output on every input below that
was run on both. SPDX License List 3.29.0, as packaged.

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| LID-1 | **An optional part of a listed text is matched as if required.** An Apache 2.0 text without its appendix gives `Pixar` first (0.9963), `Apache-2.0` second (0.9921): bandit 1.9.4, `licenses/LICENSE`. Nine of 197 licence files of one environment | run 2026-11-23 on 0.9.1; measured 2026-11-19 on 0.9.0 | yes: the handoff page (`Pixar` over `Apache-2.0`, from #286, open) |
| LID-2 | **The LGPL version 3 text alone gets no result.** fickling 0.1.12, `licenses/LICENSE` (165 lines, 1,234 words: the text FSF ships as `COPYING.LESSER`). With `--threshold 0` the first of twelve results is `copyleft-next-0.3.0` at 0.6384; no LGPL id is among them. The indexed text of `LGPL-3.0-only` has 6,888 words: the LGPL part and the whole GPL version 3 text (5,644 words in a plain copy). The same class as LID-1, with a worse end: nothing instead of a near id | run 2026-11-23 on 0.9.0 and 0.9.1; the word counts read from the packaged database | no |
| LID-3 | **An empty result gives no reason.** For LID-2, `--json` prints every field as `null`; `resolve` has a `reason` for the like case | run 2026-11-23 on 0.9.1 | no |
| LID-4 | **A copyright line in front hides the licence.** In 21 of 197 files Pitloom's second reading (the text without its copyright notice lines) names another id than LicenseID's first: `MIT-advertising`, `FSL-1.1-MIT`, `Xnet`, `X11-swapped`, where the file is MIT. A comment in LicenseID's own code says its `exact` is stricter than SPDX matching, which lets a copyright line differ | measured 2026-11-19 on 0.9.0; not run again | yes: the handoff page (PyYAML gives `Xnet`) |
| LID-5 | **A file with several licence texts gets one id, and nothing says there are more.** mypy (the MIT text, then the Python licences: `Python-2.0.1`), NumPy (its BSD text and a list of bundled licences: `LGPL-2.1-or-later`), python-dateutil (an Apache notice, then the BSD text that applies to all code: `Apache-2.0` at 0.9187), PyMdown Extensions (`MIT`) | measured 2026-11-19 on 0.9.0, four files read | no |
| LID-6 | **One text, two ids, both `exact`.** An MPL 2.0 text is exact for `MPL-2.0` and for `MPL-2.0-no-copyleft-exception`; no field says the text is shared (`variant_stated` is for `-only` and `-or-later`) | measured 2026-11-19 on 0.9.0 | partly: the handoff page asks it for URLs that map to several ids |
| LID-7 | **A notice scores as the text.** CacheControl 0.14.4, `licenses/LICENSE.txt` (13 lines that name Apache 2.0): `Apache-2.0`, `method` `text`, score 1.0, coverage 0.0571. Nothing but the coverage tells a notice from the licence | run 2026-11-23 on 0.9.1 | no |
| LID-8 | **`score` reads as a measure of fit and is a ranking key.** `Pixar` at 0.9963 is wrong, `MIT` at 0.9304 is right, a 13-line notice has 1.0. A caller that sets a threshold on it is misled | run and measured, as above | no |

What would help Pitloom most, in order: LID-1 with LID-2 (read the
optional marks of the list's templates), LID-4, LID-5 (a sign that more
than one text was found, even with one id), LID-7 (a sign that the
input is a notice), LID-3, LID-6, LID-8 (a line in the documentation).
With LID-1, LID-2 and LID-4 fixed, Pitloom's second reading and most of
its gate ([asserter-licence.md](asserter-licence.md)) could go.

### Prompt to hand over

```text
Pitloom found eight things in LicenseID 0.9.0 and 0.9.1 (SPDX License
List 3.29.0 as packaged). For each: reproduce, fix or document, add a
test and a changelog line. Report which you did, which you refused and
why. Do not touch Pitloom.

1. Optional text matched as required. `detect --top 2 -v` on the
   LICENSE of bandit 1.9.4 (Apache 2.0 without its appendix) gives
   Pixar 0.9963 before Apache-2.0 0.9921.
2. Same cause, no result at all. `detect -v` on the LICENSE of
   fickling 0.1.12 (the LGPL version 3 text alone, 1,234 words) gives
   an empty result; with `--threshold 0 --top 12` no LGPL id appears.
   The indexed text of LGPL-3.0-only has 6,888 words: it holds the GPL
   version 3 text too. Check the list's XML for an optional mark there.
3. The empty result of 2 has no reason: `--json` is all null.
4. A leading copyright line makes an MIT text match MIT-advertising,
   FSL-1.1-MIT, Xnet or X11-swapped first (21 of 197 licence files of
   one environment, 0.9.0).
5. A file with several licence texts gets one id and no sign of the
   others: the licence files of mypy, NumPy, python-dateutil, PyMdown
   Extensions.
6. An MPL 2.0 text is exact for MPL-2.0 and for
   MPL-2.0-no-copyleft-exception; no field says the text is shared.
7. A 13-line notice that names Apache 2.0 (CacheControl 0.14.4,
   LICENSE.txt) gives Apache-2.0, method text, score 1.0, coverage
   0.0571. Give a way to tell a notice from the text.
8. Say in the documentation that `score` ranks and does not measure
   fit, or give a field that does.
```

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
