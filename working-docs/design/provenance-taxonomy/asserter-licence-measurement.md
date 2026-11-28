---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Asserter and the licence field: LicenseID's answers, Pitloom's reading

See also: [asserter-licence.md](asserter-licence.md) (the rulings these
runs fed, the gate for a text match and the open decisions; this page
was part of it until 2026-11-28),
[findings-to-fix-first.md](findings-to-fix-first.md) (LID-1 to LID-9).

**Status:** a record of the code path and of runs. The code path is
read at `main` dfa11c14 (release 0.25.1, pin `licenseid>=0.10.0,<0.11`);
each run names its day, its LicenseID version and what was run. A
LicenseID match is tool output, not the truth about a licence file:
where a file was read by a person, the section says so. Paths are under
`src/pitloom/`.

## Today's detection path (dfa11c14, LicenseID 0.10.0)

Read at dfa11c14. One function reads a licence text:
`read_license_text(text, threshold=0.85, *, stated=None)`
(`extract/_license_text_match.py:367-410`); no caller passes another
threshold (grep).

1. A text under 100 characters is no reading, and the database is not
   looked up (`:127`, `:390-391`).
2. One `LicenseDetector` per process, default database (`:54-62`). A
   missing database is `license-db-missing` (`INFO:` when a licence is
   stated, else `WARNING:`), an unusable one `license-db-unusable`, each
   said once (`:88-124`); any other failure of a lookup is `DEBUG` only
   (`:404-409`).
3. Two readings: the text as written and, when it has copyright notice
   lines, without them (`_reading_inputs`, `:254-261`). Each is
   `detector.detect(text)` with no option (`:264-270`).
4. **Several texts.** When either reading holds two or more List texts
   (`texts` of the first result, or `detector.texts()` when there is no
   result), the answer is none, stated or not, and the caller's search
   over licence files stops (`:273-305`, `:399-400`; #554, #563).
5. Only the reading(s) with the best top score count (`:313-322`). A
   licence the caller states wins a near-tie: within 0.01 of the top,
   and at the 1.0 cap only if it fits no worse in `similarity` or
   `coverage` capped at 1 (`_stated_among`, `:173-193`). Else the top id
   stands when it scores 0.85 or more and no other licence family
   (the id without `-only`/`-or-later`) is within 0.01 without fitting
   worse (`_decisive`, `:231-251`).
6. Fields read: `expression`, `score`, `similarity`, `coverage` (only to
   judge a runner-up), the number of `texts`. Not read: `exact`,
   `same_text`, `variant_stated`, `method`, `lists` (grep). The API
   `detect()` has no `reason` (LicenseID's output documentation: "The
   API `detect()` returns an empty list and has no such field").

Routes (read):

| Route | Stated licence for the tie | Result written |
| --- | --- | --- |
| project licence sources: `CITATION.cff`, `codemeta.json`, then sixteen root names (`extract/_license_detect.py:33-35`, `:99-104`, `:185-220`) | the manifest's | manifest silent: declared; manifest states one: concluded, and a conflict Annotation (role `detected`) when they differ (`assemble/spdx3/deps_license.py:287-317`); no message |
| manifest licence text (`stated_license`, `extract/_license.py:219-240`) | none | the id, declared; unmatched text as written |
| `embed-wheel --project-dir` (`_embed_overlay.py:71-88`) | the wheel's | concluded |
| installed dependency whose Core Metadata names no SPDX licence and whose classifiers name at most one (`assemble/spdx3/_deps_license_files.py:106-175`) | the classifier expression | declared; beside stated text that reads otherwise, two declared licences and a conflict Annotation with two `declared` candidates; no message |
| Hub, card licence absent or vague (`extract/remote/huggingface_fetch.py:269-315`, `:386-404`) | none | declared; no `Tool` segment (PIT-11) |

A match is written `Source: <file> | Method: licenseid_detection |
Tool: licenseid==<version>` (`extract/_license.py:93-97`, `:118-121`;
the Hub leaves out `Tool`). Nothing is said for a file below the gate,
a near-tie, a file of several texts, or a G2 difference (PIT-18).
LicenseID's own warnings are relayed as `licenseid: ...` lines,
`variant not stated` at `INFO:` (`extract/_licenseid_relay.py:60-75`).

## 2026-11-19 and 2026-11-23: LicenseID 0.9.0 and 0.9.1

Run on LicenseID 0.9.0 (`detect`, SPDX License List 3.29.0 as packaged),
2026-11-19; the first result, and the second where it ties. Not run
again on 0.10.0 in this form: the run of 2026-11-28 below covers some
of these inputs.

| Input | `expression` | `method` | `exact` | `score` | `variant_stated` |
| --- | --- | --- | --- | --- | --- |
| the GPL version 3 text, bare | `GPL-3.0-only`, then `GPL-3.0-or-later` | `text` | false | 1.0, 1.0 | false |
| the id `GPL-3.0` | `GPL-3.0`, kept as written | `id` | true | 1.0 | false |
| `GPL-3.0 or later` | `GPL-3.0-or-later` | `id` | true | 1.0 | true |
| `GPLv3+` | `GPL-3.0-or-later` | `id` | false | 1.0 | true |
| `Apache License, Version 2.0` | `Apache-2.0` | `name` | false | 1.0 | none |
| an Apache 2.0 text, its copyright line filled in | `Apache-2.0` | `text` | false | 1.0 | none |
| OL-5 of the examples: an Apache 2.0 text without its appendix | `Pixar`, then `Apache-2.0` | `text` | false | 0.9947, 0.9937 | none |

- `variant_stated` was new in 0.9.0: whether the input says which of
  `-only` and `-or-later` is meant. For the bare GPL text it is false,
  with `WARNING: input: variant not stated: GPL-3.0; using
  GPL-3.0-only`; `--variant as-written` gave the same answer for the
  text.
- `exact` was narrower than in 0.8.4: false for a value a rewrite rule
  read (`Apache License, Version 2.0`). For a text it is false, as in
  0.8.4, when a copyright line is filled in: nearly every real licence
  file is not exact.
- A wrong match was unchanged on 0.9.0: OL-5 gave the same ids and
  scores as in 0.8.4.
- LicenseID 0.9.1 (run 2026-11-23, same list 3.29.0) gave the same
  output as 0.9.0 on what was tried: `resolve` of twelve values (the
  ids and names of the table, two licence URLs, a classifier) and
  `detect` of five files (a bare GPL version 3 text, an Apache 2.0
  text with and without its appendix, a 13-line Apache notice, an LGPL
  version 3 text). The category and `trust` tables of
  `licenseid.resolvertypes` are equal in the two releases.

## 2026-11-19: the gate over 197 licence files, LicenseID 0.9.0

Measured on 2026-11-19 with LicenseID 0.9.0; **not run again on 0.9.2
or later, nor on 0.10.0**. Every count in this section is of that day
and version.

`detect()` of LicenseID 0.9.0 on the licence files of the 166
distributions installed in the repository's environment, and Pitloom's
rule of that day on the same files (the code at 257b7260, run with
0.9.0). The files were picked by name (`LICEN*`, `COPYING*`) in each
metadata folder: 198, of which one is not a licence file (LicenseID's
own SBOM, by its name) and is left out, so 197. The rule of that day
read the text as written and without its copyright notice lines, and
took the better reading. It named the top id when the score was 0.85
or more and no other licence family was within 0.01 of it, unless that
one fitted the text worse (`similarity`, `coverage`). A licence the
manifest states wins a near tie; none was given here. (The
several-texts rule of #554 and #563 did not exist yet.)

| LicenseID's first result | Files | The rule names an id | Of which not LicenseID's first id |
| --- | --- | --- | --- |
| `exact` true | 20 | 18 | 0 |
| score 1, not exact | 108 | 108 | 0 |
| score 0.85 to 1 | 43 | 39 | 10 |
| score under 0.85 | 26 | 11 | 11 |

Findings of that day (LicenseID 0.9.0, 2026-11-19, not run again on
0.10.0):

- `exact` is too narrow to be the gate: 20 files, each `Apache-2.0` or
  `MPL-2.0`. A filled-in copyright line makes a text not exact, so no
  MIT, BSD or ISC file is exact.
- `exact` is not one id either. The two MPL files are exact for
  `MPL-2.0` and for `MPL-2.0-no-copyleft-exception`: one text, two ids.
  On 0.9.0 no field said so; since 0.9.2 `same_text` names the twin
  (LID-6). The rule called it a tie and named none, and still does
  (2026-11-28 below).
- `score` is not the gate. It is a ranking key: 1.0 for a 13-line
  Apache notice (`coverage` 0.06), 0.92 for a file with `similarity`
  0.47. `Pixar` at 0.9963 is wrong and `MIT` at 0.9304 is right.
- The second reading did much of the work. In 21 files it named another
  id than LicenseID's first (`MIT-advertising`, `FSL-1.1-MIT`, `Xnet`,
  `X11-swapped` to `MIT`). The head of five was read by a person
  (attrs, pytest, pydantic, MkDocs, Pygments): each begins as the
  licence the second reading names.
- Wrong on that day, nine files: an Apache 2.0 text without its
  appendix gave `Pixar` (six read: none has the appendix, and section 6
  is Apache's). The SPDX License List template of `Apache-2.0` (3.29.0)
  marks the appendix as optional text; `Pixar` differs in section 6.
- One id for a file that holds several, four read: mypy (the MIT text,
  then the Python licences, gave `Python-2.0.1`), NumPy (its own BSD
  text and a list of bundled licences, gave `LGPL-2.1-or-later`),
  python-dateutil (an Apache notice, then a BSD text that "applies to
  all code", gave `Apache-2.0`), PyMdown Extensions (MIT and
  third-party parts, gave `MIT`).
- Not a licence text: a notice (CacheControl's 13 lines name Apache 2.0
  and score 1.0) and a pointer (packaging's `LICENSE` names two other
  files; no id, rightly).
- Under the gate: of the 26 first results under 0.85, the second
  reading replaced 11 and named none for 15; all 19 files that did not
  pass belong to a distribution whose Core Metadata states a licence.

## 2026-11-28: LicenseID 0.10.0 on 15 files and five probes

Run on 2026-11-28 by the agent that re-based
[asserter-licence.md](asserter-licence.md), with LicenseID 0.10.0 (SPDX
License List 3.29.0, its own database, a scratch environment), through
the API `LicenseDetector.detect()` and `LicenseDetector.texts()` and,
for two files, `licenseid detect -v --top 2`. Each file was read as
written and without the lines that `COPYRIGHT_NOTICE_LINE_RE` matches
(`extract/copyright_notices.py:57-61` at dfa11c14), as Pitloom reads
it.

Files: the 13 licence files of `tests/fixtures/license-texts/` at
dfa11c14, PyYAML 6.0.3's and requests 2.34.2's `LICENSE` from the sdist
fixtures of `tests/fixtures/real-world-projects/setuptools/`. Pitloom
itself was not run: the column "Pitloom's gate" is worked by hand from
these numbers with the rule as read at `_license_text_match.py:231-251`
and `:290-305`, with no licence stated.

| File | First result (as written) | Second | `texts` | Pitloom's gate, nothing stated |
| --- | --- | --- | --- | --- |
| attrs 26.1.0, check-wheel-contents 0.6.3, iniconfig 2.3.0, pytest 9.1.1, RapidFuzz 3.14.5, PyYAML 6.0.3 | `MIT` 1.0 | `JSON`, 0.9865 to 0.9965 | `MIT` | `MIT` |
| pydantic 2.13.5 | `MIT` 0.9929 (without notice 1.0) | `JSON` | `MIT` | `MIT` |
| ast_serialize 0.11.1 | `MIT` 0.9304 (without notice 0.9456) | `JSON` 0.9266 | `MIT` | `MIT` |
| wcwidth 0.8.3 | `MIT` 0.9197 | `MIT-0` 0.8321 | `MIT` | `MIT` |
| astroid 4.3.2 | `LGPL-2.1-only` 1.0, `variant_stated` false, `same_text` the `-or-later` | `LGPL-2.1-or-later` 1.0 | `LGPL-2.1-only` | `LGPL-2.1-only`, unmarked |
| fickling 0.1.13 | `LGPL-3.0-only` 1.0, as astroid | `LGPL-3.0-or-later` 1.0 | `LGPL-3.0-only` | `LGPL-3.0-only`, unmarked |
| pylint 4.1.1 | `GPL-2.0-only` 1.0, as astroid | `GPL-2.0-or-later` 1.0 | `GPL-2.0-only` | `GPL-2.0-only`, unmarked |
| requests 2.34.2 | `Apache-2.0` 1.0 (similarity 0.9927, coverage 1.0144) | `Pixar` 0.9963 (0.9913, 1.0043) | `Apache-2.0` | none: a near-tie of two families |
| types-setuptools 84.2.0.20261122 | `Apache-2.0` 1.0 | `Pixar` 0.8785 | `Apache-2.0 MIT` | none: several texts; the search stops |
| numpy 2.5.5 | no result | - | `BSD-3-Clause BSD-3-Clause-Open-MPI GPL-3.0-only` (from `texts()`) | none: several texts; the search stops |

- In none of the 15 files does the reading without the notice change
  the first id. LID-1 (requests) and LID-4 (attrs, pytest, PyYAML,
  pydantic) are fixed for these files.
- For every file with an answer, `texts` is exactly the first id but
  for types-setuptools: by LicenseID's caller rule (its output
  documentation, "Which field to read") each of these would be
  declared, requests included, and types-setuptools would declare
  `Apache-2.0` and `MIT` each on its own.
- The commit that pinned 0.10.0 (6c2de8d7) says the full suite passed
  and that ast_serialize and wcwidth now give `MIT` with no licence
  stated; that agrees with the last column. Not run here.

Five probes, run the same day with a copy of Pitloom's gate functions
(`_family`, `_fit`, `_fits_worse`, `_decisive`, the best-reading choice
and the several-texts test, copied from dfa11c14, no `stated`) on the
real 0.10.0 output. The texts are not real files: three are the
normalised texts LicenseID stores for the licence (its database's
`license_texts`), one is a 12-line Apache header written for the probe.

| Probe | LicenseID 0.10.0 | `texts` | The copied gate |
| --- | --- | --- | --- |
| `MPL-2.0` as stored | `MPL-2.0` exact 1.0, `same_text` the no-copyleft twin; the twin exact 1.0 | `MPL-2.0` | none: a near-tie of two families |
| `Apache-2.0` as stored, cut before its appendix | `Apache-2.0` 1.0, then `Pixar` 0.9947 | `Apache-2.0` | none: a near-tie |
| a 12-line Apache header with a copyright line | `Apache-2.0` 1.0, coverage 0.0564; `FSL-1.1-ALv2` 0.9681 | none | `Apache-2.0` |
| the MIT text, then the Apache text | no result | `MIT Apache-2.0` | none: several texts |
| the Apache text, then the MIT text | `Apache-2.0` 1.0 | `Apache-2.0 MIT` | none: several texts |

Not run on 0.10.0: the 197 files, the real files of mypy, CacheControl,
pathspec, bandit, rfc8785 and OL-5 of the examples. What LicenseID's
documentation says of mypy (`MIT`, `texts` `MIT Python-2.0.1
BSD-2-Clause`) is read, not run.
