---
Created: 2026-11-23
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Findings to fix first: LicenseID and Pitloom

See also: [README.md](README.md) (the claim model),
[asserter-licence.md](asserter-licence.md) (the gate for a text match) and
[asserter-licence-measurement.md](asserter-licence-measurement.md) (its
measurement), [source.md](source.md) (a source that can change),
[renames-and-migration.md](renames-and-migration.md) (hazards for the
code stage, the sweep against `main`),
[findings-to-fix-first-prompts.md](findings-to-fix-first-prompts.md)
(the two hand-over prompts).

**Status:** list, written 2026-11-23. The taxonomies are agreed (stage
(c)); the code stage waits for the fixes here (the user, 2026-11-23).
Releases 0.25.0 and 0.25.1 are out (2026-11-27 and 2026-11-28), so
the fixes may start, each on the user's word; none has. The list was
read again on `main` on 2026-11-28
([third look](#third-look-on-main-2026-11-28-dfa11c14-release-0251)).
These are things the taxonomy work came across
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
([asserter-licence-measurement.md](asserter-licence-measurement.md))
and was not run again.
The last column is the same command on the same files with 0.9.2,
run on 2026-11-24 beside 0.9.1 (which gave the old output again);
"open" means the output is the same as before.

| # | Finding | On `main` | With 0.9.2 |
| --- | --- | --- | --- |
| LID-1 | **An optional part of a listed text is matched as if required: a wrong id first.** An Apache 2.0 text without its appendix gives `Pixar` (0.9963), then `Apache-2.0` (0.9921): bandit 1.9.4. Nine of 197 files | yes: the handoff page (`Pixar` over `Apache-2.0`, from #286, open) | fixed: `Apache-2.0` first (1.0), `Pixar` second |
| LID-2 | **The same cause: no result at all.** The LGPL version 3 text alone (fickling 0.1.12; 1,234 words, the text FSF ships as `COPYING.LESSER`) gets an empty result. With `--threshold 0` the first of twelve is `copyleft-next-0.3.0` at 0.6384, and no LGPL id is among them. The indexed text of `LGPL-3.0-only` has 6,888 words: the LGPL part and the whole GPL version 3 text (5,644 words in a plain copy) | no | fixed: `LGPL-3.0-only`, `variant_stated` false, with a warning that the variant is not stated |
| LID-3 | **An empty result gives no reason.** For LID-2, and for pydantic in LID-4, `--json` prints every field as `null`; `resolve` has a `reason` in the like case | no | fixed: a new field `reason` (`below threshold`); no nearest candidate |
| LID-4 | **A title line and a copyright line hide the licence.** Four plain MIT texts: attrs 26.1.0 gives `MIT-advertising` (0.8724), pytest 9.1.1 `FSL-1.1-MIT` (0.9151), PyYAML 6.0.3 `Xnet` (0.9023), and pydantic 2.14.3 an empty result. The first, second and fourth begin "The MIT License (MIT)" and a copyright line; PyYAML has no title and two copyright lines. tomli 2.5.0 begins "MIT License" and gives `MIT` at 1.0. In 21 of 197 files Pitloom's second reading (the text without its copyright lines) names another id than LicenseID's first. Only the first three lines of each file were read here | partly: the handoff page (PyYAML gives `Xnet`); the empty result is new | fixed: `MIT` for all four |
| LID-5 | **A file with several licence texts gets one id, and nothing says there are more.** mypy 2.4.1 (the MIT text, then the Python licences: `Python-2.0.1`, 0.9203), NumPy 2.2.6 (its BSD text and bundled licences: `LGPL-2.1-or-later`, 0.9472), python-dateutil 3.0.0 (an Apache notice, then the BSD text that applies to all code: `Apache-2.0`, 0.9187), PyMdown Extensions 12.3 (`MIT`, 0.9342) | no | open |
| LID-6 | **One text, two ids, both `exact`.** The MPL 2.0 text of pathspec 1.1.1 is exact at 1.0 for `MPL-2.0` and for `MPL-2.0-no-copyleft-exception`; no field says the text is shared (`variant_stated` is for `-only` and `-or-later`) | partly: the handoff page asks it for URLs that map to several ids | fixed: a new field `same_text` names the other id |
| LID-7 | **A notice scores as the text.** CacheControl 0.14.4 (13 lines that name Apache 2.0): `Apache-2.0`, `method` `text`, score 1.0, coverage 0.0571. Nothing but the coverage tells a notice from the licence | no | open |
| LID-8 | **`score` reads as a measure of fit and is a ranking key.** `Pixar` at 0.9963 is wrong, a 13-line notice has 1.0. A caller that sets a threshold on it is misled | no | open: nothing on `score` in the README of the package |
| LID-9 | **`coverage` goes above 1, and no page says what it measures.** NumPy 2.2.6: 1.7164 for the first result and 34.5321 for `BSD-3-Clause`; mypy 2.4.1: 1.2882; PyMdown Extensions 12.3: 3.6882 | no | open: same values, nothing in the README of the package |

What would help Pitloom most, in order: LID-1, LID-2 and LID-4 (the
SPDX matching guidelines let optional text be absent and a title or a
copyright notice differ), then LID-3, LID-5 (a sign that more than one
text was found), LID-7 (a sign that the input is a notice), LID-6,
LID-8 and LID-9 (the documentation). With the first three fixed,
Pitloom's second reading and most of its gate
([asserter-licence.md](asserter-licence.md)) could go. They are
fixed in 0.9.2 for these files; the count over the 197 files was
not made again, and Pitloom's code is as it was (its range
`>=0.9.0,<0.10` takes 0.9.2, and its licence tests pass with it).

**After 0.9.2** (run 2026-11-26 to 2026-11-28 on the licence files of
one Python 3.10 environment, 223 files, each release beside the one
before it; the 197-file count was not made again):

| Release | What it changed for these findings |
| --- | --- |
| 0.9.3 | LID-5: a new field `texts` lists the List ids whose whole text the input holds. LID-7, LID-8, LID-9: `docs/output.md` says what `score` (a ranking key), `similarity` and `coverage` measure, and gives a rule for a caller (declare the answer when `texts` is exactly the answer; `texts` empty with `coverage` under 0.8 is a notice) |
| 0.9.4 | `texts` is in the order of the file, and a record of no answer carries it. A text answer stands only when its text is the first whole text of the file; otherwise no answer, `reason` `several texts` (NumPy 2.2.6 and mypy 2.4.1 give no answer now). A text whose holder or project name is not the List's is found (SymPy's BSD text) |
| 0.10.0 | whole texts are looked for first: an MIT text with a few more lines answers `MIT` (wcwidth 0.9.5 gave `JSON` before). Database build 10; an older build is refused |

So LID-1 to LID-9 are answered in LicenseID. Still open there, handed
over on 2026-11-28: a file that holds a whole text and gets no answer
because it holds more (ruff 0.17.6, tqdm 4.70.1, NumPy 2.2.6), the
Mozilla Public License header notice (certifi), and exception texts
(a prompt for these was written on 2026-11-28; it is not on a page).

Pitloom requires `licenseid>=0.10.0,<0.11` since 0.25.1, but its
second reading and its gate are still there and now differ from
LicenseID's own rule for a caller: [asserter-licence.md](asserter-licence.md).

The prompt to hand over:
[findings-to-fix-first-prompts.md](findings-to-fix-first-prompts.md#prompt-for-licenseid-written-2026-11-23).

Not read for this page: the list's XML for the optional marks (LID-1,
LID-2), and the full text of the four MIT files of LID-4.

## Pitloom

Read at the draft's base 257b7260 unless a row says `main`. Each needs a
second look on `main` before work starts: 135 commits lie between.
Read again on `main` dd31412b on 2026-11-23, for the prompt
([findings-to-fix-first-prompts.md](findings-to-fix-first-prompts.md#prompt-for-the-pitloom-fixes-written-2026-11-23)):
PIT-1, PIT-2 (one of its five sites), PIT-3, PIT-4, PIT-7, PIT-8, PIT-9
and PIT-12. The prompt gives the file and line of
each, and marks every other item as read at the base or to check.

### Second look on `main` (2026-11-24, 6cb6183f)

No code was changed and nothing was run: the items the prompt marks
"base" or "check" were read again. "Agent" is a search by a cheaper
model; every line it quoted that is named here was then read.

| # | State on `main` | How known |
| --- | --- | --- |
| PIT-2 | The five sites stand: `_setuptools_options.py:456` (the whole string compared), `_optional_dependencies.py:60-62`, `_setuptools_dynamic.py:286` and `lock/cascade.py:240-242` (each parses the string again), `scanner.py:218` (a prefix test, to rewrite a copied path). More of the kind, so the work is wider than five sites: `core/evidence.py:223` reads the `Evidence` level back, and the encoders decide from the parsed string (`_provenance_encoders.py:87` and `:95`, `deps_license.py:204`, `_license_elements.py:379`) | agent; the five sites read |
| PIT-5 | Stands, narrower. With no `sha` the revision is none, and the card, the three config files and the licence files are each fetched at `main` (`huggingface_fetch.py:314-324`, `_hub_files.py:150`), with one `WARNING:` (`hub-revision-unpinned`). When `model_info` fails there is no list of licence files, so none is fetched; when it answers without a `sha` they are. Not read: whether the file reader resolves `main` once | agent; three places read |
| PIT-6 | Stands. The provenance is `Source: PyPI JSON API \| Package: <name>` (`deps_installed.py:83`, `deps.py:142` and `:150`); the version of the release read is in no segment and is not kept (`info["version"]` is not read). The PyPI URL target does record it (`Method: latest-release` with a `Value`): the same shape would do | agent; the builder read |
| PIT-9 | The test is unchanged (`_provenance_encoders.py:79-87`, used at `deps_license.py:204`). No reader was found that hands over a licence with no source: the main package, a PyPI dependency, an installed dependency, a model and a dataset each pass a `Source:` or a default. Not traced: fragments and enrichment. The branch may be reachable from outside input only | read |
| PIT-10 | Out of date for GGUF: since #517 a header over a bound is read in part, the fields read are kept, and one `over-cap` warning says where it stopped (`gguf.py`, `_warn_partial`); tensor shapes are then absent. For NumPy, PyTorch, Safetensors and an archive member, `ModelOverCap` gives a stub (the file and its format) and one warning, not an error (`scanner.py:333-342`). Open: whether the stub's file carries its size and digest, and what a parameter count says then | read, not run |
| PIT-11 | All three stand: `wheel.py:134`, `:136` and `:151` against `sdist.py:101`, `:105` and `:110`; `huggingface_fetch.py:289-292` and `:378` against `_license.py:93`; `onnx.py:444` against `fasttext.py` and `numpy.py:296` | agent; the lines read |
| PIT-14 | The sentence on the page is corrected (2026-11-24). The same claim stands in the message catalogue: the summary of `license-conflict` (`messages/_license_expression.py:191`) and the pages generated from it in `docs/` and in two skills. That needs a change of source and the reference generated again | read |

### Third look on `main` (2026-11-28, dfa11c14, release 0.25.1)

Every finding was read again by a search agent (238 commits and two
releases after the second look); nothing was run. The lines named
here for PIT-2 (`is_license_concluded`), PIT-3, PIT-4, PIT-8, PIT-11
(the Hub string) and PIT-12 were then read by the session that
writes this; the others are the agents' reading. **No release fixed
any finding.** Where a row says "stands", the rows below hold as
written; the file and line of the prompt may have moved.

| # | State on `main` dfa11c14 |
| --- | --- |
| PIT-1 | Stands, no site moved. Counted: 62 strings with an interpolated value and 4 suffix constants (55 of the 62 in `extract/ai_model/`), beside 61 whole literals. Of the 27 values that are not the `Source:` base, 24 come from a fixed list or constant, one from a builder, one is a number, one was not traced: no text of a file or of the network enters a `Field:` or `Method:` segment |
| PIT-2 | Stands, wider again. Moved: `_setuptools_dynamic.py:288`, `scanner.py:231` (now also each dataset's provenance), `deps_license.py:216`. Changed in 0.25.1: `is_license_concluded` is `return not _source_name(entry)` (`_provenance_encoders.py:79`; `THIRD_PARTY_SOURCES` is gone), and `_license_elements.py:318-326` compares the string and parses it. More sites: `_setuptools_options.py:225` and `:307`, `_fragments_generated.py:61`, `_fragments_model_names.py:89`, `_fragments_evidence.py:62` (a test on the spelling `not_measured`), the key `(value, role, source)` at `deps_installed.py:295`, the credential scan `export/_spdx3_credentials/_find.py:140` (the schema compared with `==`: a new schema version stops its reading of notes, silently) and `scripts/extract_wheel_sbom.py` |
| PIT-3 | Stands, unchanged: `core/models.py:198-199`. Two routes reach the seed: `assemble/spdx3/document.py:187` and `assemble/_model_generator.py:195`. The tests pin the id through the real reader for `pylock.toml` and `poetry.lock` only; the other locks by a string typed in the test |
| PIT-4 | Stands. The commit is resolved (`extract/remote/git.py:264`) and nothing outside that module reads it |
| PIT-5 | Stands as in the second look. New: a model not found is refused, and a revision named in the URL gets a `WARNING:` (`hub-revision-unpinned/url`); the files are still read at the default branch |
| PIT-6, PIT-7, PIT-12, PIT-13, PIT-21 | Stand. PIT-7 is now at `extract/remote/huggingface_field.py:381-388`. PIT-21: the Hub library is first imported at `extract/remote/huggingface.py:379`, and it reads the variable at import |
| PIT-8 | Other shape. A check of the name exists (`_embed_overlay.py:119`): when the directory's project is not the wheel's, a `WARNING:` (`metadata-conflict`) and its authors are not taken. It runs only when the project states authors. No check of the version; the directory's licence is still read (`_embed_build_sbom.py:413`) |
| PIT-9 | Narrower. Since 0.25.1 only a value with no source is concluded, and every reader passes a source. Reached from a library caller's own metadata only (an empty provenance string, or one with no `Source:`) |
| PIT-10 | As in the second look. A stub carries no size; its file element, with the digest, is separate (`assemble/spdx3/ai.py:243` reads the digests of the files); no size is written for it. Not run |
| PIT-11 | All three stand (`wheel.py:134-151`; `huggingface_fetch.py:308-313` and `:402`; `onnx.py:448`) |
| PIT-14 | The page is right; the catalogue is not: `messages/_license_expression.py:191` and the three pages generated from it |
| PIT-16 | Stands: `Tool: magika==<package version>`, no code reads a model version |
| PIT-17 | Answered: `model-index` is kept as it is (`hf.model_index` in the package's metadata), and nothing reads it as results |
| PIT-18 | Stands: a manifest licence against the licence of a licence file writes a conflict Annotation and no warning (`deps_license.py:287-317`) |
| PIT-19 | `_setuptools_options.py:102-109`: the `setup.py` value wins when it is given (its value is not empty), or when `setup.cfg` lacks the key |

New since the second look, and not a finding of its own: a
dependency's licence is declared (pull request 569), also when read
from the licence files of its installed copy; a licence file with
several texts gives no licence and ends the search (554, 563). Both
are in [asserter-licence.md](asserter-licence.md).

The rulings of 2026-11-28 on the draft itself:
[resweep-rulings.md](resweep-rulings.md). The prompt for the fixes
was written for dd31412b and is not yet rewritten to this look.

### Groundwork the code stage needs, with no change of output

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-1 | **Provenance segments built by hand.** About 75 f-strings and suffix constants write ` \| Field: ...` or ` \| Method: ...` without `provenance_segment`, most in `extract/ai_model/`. The lint test (`tests/test_provenance_builders_lint.py`) allows it: it is strict for every key but `Field:` and `Method:`, and for those two it refuses only an interpolated name that looks external (`entry`, `path`, `url`, `name` and the like). So no test shows that a value put into such a segment holds no `\|` (one would forge a segment). Three interpolations were traced (Safetensors, CRFsuite): each comes from a fixed list. One hand-written string feeds the document id (PIT-3): the `poetry.lock` provenance at `extract/project/pyproject.py:358`. To do: trace the rest, send all through the builders, then make the test strict for the two keys | read on `main` dd31412b, 2026-11-23: the lint test in full; three values traced, the rest not. The `pyproject.py` site read on `main` 6cb6183f, 2026-11-24 | no |
| PIT-2 | **Provenance strings used as data.** Five sites compare or parse one again (`_setuptools_options.py`, `_optional_dependencies.py`, `_setuptools_dynamic.py`, `lock/cascade.py`, `scanner.py`). A change of wording changes behaviour. Carry a typed value beside the string | read at the base | no |
| PIT-3 | **The document id hangs on a provenance string.** The provenance of `locked_dependencies` is hashed into the document UUID, so a reworded label changes every SPDX id of such a document. The strings that reach the seed are those of the lock cascade (`extract/lock/cascade.py`) and the hand-written `poetry.lock` string of `pyproject.py:358`; `_DEFAULT_LOCKED_PROVENANCE` does not reach it. Today's ids are pinned by tests since 2026-11-24 (`tests/core/test_models.py`, pull request 533; the poetry string had no test that a rewording would fail). Left: seed it by a function of its own that keeps today's text | the call from `document.py` and the `pyproject.py` string read on `main` 6cb6183f, 2026-11-24; the cascade's strings and the tests from the session that wrote them, not read here | no |

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
| PIT-21 | **The Hub library makes a request of its own on the first Hub read of a process**: `GET {HF_ENDPOINT}/api/agent-harnesses`, with no token, and a cache file under `HF_HOME` for 24 hours. Ruled 2026-11-24: the documentation says so now (`docs/ai-model-formats.md`); after the 0.25.0 cut the CLI, the build hook and the Action switch it off (`HF_HUB_DISABLE_TELEMETRY`), keeping a value the user set, and the library API leaves it to the caller. To read first: where the variable has to be set (the library reads it at import) and what else the switch turns off | measured by the session that fixed PIT-20, with `huggingface_hub` 2.4.0; the fetch function and the gate read in 2.2.0; notes in [hub-loopback-socket-flake.md](../../implementation/hub-loopback-socket-flake.md) | no |

### Tests and CI

| # | Finding | Seen | On `main` |
| --- | --- | --- | --- |
| PIT-20 | **Fixed 2026-11-23 (pull request 528). Four Hub loopback tests failed now and then on an unclosed socket.** `tests/extract/remote/test_hub_loopback.py`, macOS, Python 3.13: `ResourceWarning: unclosed <socket.socket ...>` at `huggingface_hub/utils/_detect_agent.py`, a failure by `filterwarnings = error`; the rerun failed the same way on Windows. Cause: on its first agent detection in a process, `huggingface_hub` (2.4.0 in that run) asks the real Hub (`constants.ENDPOINT`) for a registry; the loopback guard of `tests/conftest.py` refused that `connect` with a `RuntimeError`, and `socket.create_connection` closes its socket on an `OSError` only. Seen only when a worker's first detection falls in a `loopback` test. Fix: the guard closes the socket it refuses; no warning filter, no library switch. The patch of the library's private `_fetch_registry` from pull request 524 covered one file of two and is removed. Regression test: `test_a_refused_connection_leaves_no_open_socket` | CI of pull request 519, run 45168805298, both attempts; run on demand 2026-11-23, the registry reset before each test: 19 tests failed before the fix, none after (Python 3.10 with 2.2.0, 3.13 with 2.4.0) | no |

### To look into, no fix known

| # | Question | What is known |
| --- | --- | --- |
| PIT-15 | Why the Hub's parameter total and Pitloom's own sum differ | in 15 of 128 repositories (benchmark, 2026-11-12); the cause was not looked for |
| PIT-16 | Whether a Magika package version fixes its model | `Tool: magika==x` is written as if it did; no code reads the model's version |
| PIT-17 | Whether a card's `model-index` is read | two examples are marked "to check" ([examples/originator.md](examples/originator.md), OD-11; [examples/other-party.md](examples/other-party.md), PT-9) |
| PIT-18 | Whether the licence conflict of the main package still writes no warning | read at the base; `main` has a `license-conflict` message for another case |
| PIT-19 | The order in which setuptools merges `setup.py` and `setup.cfg` | taken from the code (#287), not read again |

### Rulings on the Pitloom fixes (2026-11-23)

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

The prompt itself:
[findings-to-fix-first-prompts.md](findings-to-fix-first-prompts.md#prompt-for-the-pitloom-fixes-written-2026-11-23).

## What is not here

The work the taxonomy itself asks for (keys, labels, the licence
relationships, schema versions): hazards 4 to 15 of
[renames-and-migration.md](renames-and-migration.md). PIT-1 to PIT-3
are its hazards 3, 2 and 1, listed here because they change no output
and can go before it.
