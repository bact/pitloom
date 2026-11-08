---
Created: 2026-11-06
Last-Modified: 2026-11-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# LicenseID upstream issues

See also: [adoption-built.md](adoption-built.md)
(how Pitloom adopted LicenseID 0.7).

Findings from the Pitloom adoption of LicenseID 0.7, kept so they are not
lost.

- **Status:** drafted, not yet filed upstream.
- **Where to file:** the LicenseID repository, as one issue.
- **Who files:** the maintainer.
- **Pitloom dependency:** Pitloom 0.23.3 requires `licenseid>=0.8.1,<0.9`
  (0.23.2: `>=0.7.3`, 0.23.1: `>=0.7.2`; 0.23.0: `>=0.7.1`).
- **Drafts:** an earlier draft covered 0.7.0 only (nine findings). The text
  below is the current one for 0.7.0 to 0.7.3 (eleven findings; 0.7.2 fixes
  finding 1, 0.7.3 fixes finding 11); the earlier draft is superseded and
  has no finding the current one lacks.

## Index of findings

Severity: **contract** = behaviour a caller cannot rely on or that
contradicts the documented meaning; **process** = missing documentation or
a hook; **edge** = unusual input.

| # | Finding | Severity | Pitloom workaround | 0.8.1 |
| - | - | - | - | - |
| 1 | Short word detected as a licence | contract | none | fixed (0.7.2) |
| 2 | `\v`, `\r`, U+2028 read as white space | edge | none | reproduces |
| 3 | `coverage` above 1 | contract | Pitloom clamps it | reproduces |
| 4 | Messages name `--db` and a networked command | process | own line names `--source packaged` | reproduces |
| 5 | When a database warning is said once | process | none | reproduces |
| 6 | Deprecated ids' List names resolve to nothing | contract | 14 names in `_license_names.py` `UNREAD_LISTED_NAMES` | reproduces |
| 7 | `trust: none` answers are hard to use | process | special-cases the category | reproduces |
| 8 | `components` empty for most answers | contract | none | reproduces |
| 9 | Database is a black box | process | none | reproduces |
| 10 | Non-ASCII space before "or later" has no step | contract | none | reproduces |
| 11 | Apache name variants read inconsistently | edge | none needed | fixed |

The `0.8.1` column: findings 2, 6 and 10 were re-run on LicenseID 0.8.1
(2026-11-08) and still reproduce; 1 and 11 stay fixed; the others carry their
0.7.3 result and were not re-run.

## Issue text

The text below is ready to paste. Headings are one level lower than in the
issue.

## LicenseID 0.7.0 to 0.7.3: findings from the Pitloom adoption

Pitloom 0.23.0 requires `licenseid>=0.7.1,<0.8` (Pitloom PRs #437, #440, #445).
The points below were found on 0.7.0 and **all still reproduce on 0.7.1** (PyPI
wheel, CPython 3.10.20): the reproducers give the same output on both, apart
from `resolver.version`; 0.7.1 changes no database, warning or components code
and ships the same packaged List (3.29.0, byte-identical
`spdx-bundle.json.gz`). Item 10 is new in 0.7.1. **0.7.2 fixes item 1**
(#161); items 2 to 10 give the same output on 0.7.2, which keeps the
database build (v3), the normalisation (v2) and the packaged List
(byte-identical). **0.7.3 fixes item 11** (#172); items 2 to 10 give the
same output on 0.7.3, which changes only the reading of a name and a version
and keeps the database build, the normalisation and the packaged List
(byte-identical). Each reproducer was run with
`HOME` set to a scratch directory and a database built by `licenseid update`
(SPDX License List 3.29.0), unless a step says otherwise. Common setup:

```python
import licenseid
from licenseid import LicenseDetector, detect, resolve
det = LicenseDetector()
```

### 1. A short word is detected as a licence (F10)

```python
[(d["expression"], d["method"], d["score"], d["coverage"]) for d in det.detect("Foo")[:2]]
det.is_spdx(text="Foo"), det.is_osi(text="Foo")
```

- Actual (0.7.1): `[('3D-Slicer-1.0', 'text', 1.0, 0.0006), ('PHP-3.0',
  'text', 1.0, 0.0022)]`; `is_spdx` `True`, `is_osi` `False`.
- Expected: no detection (or a score far below 1) for a text that covers 0.06%
  of the licence; `is_spdx`/`is_osi` `None` (no licence found), not
  `True`/`False`.
- Fixed in 0.7.2 (#161): `[]`; `is_spdx` and `is_osi` `None`. Each call
  warns `input: too few words for text: not found: Foo`. Drop this item
  from the issue.

### 2. `\v`, `\r` and U+2028 are read as white space (F15, remainder)

```python
for v in ["MIT\x0bOR ISC", "MIT\rOR ISC", "MIT\u2028OR ISC", "MIT\x1fOR ISC"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"], r["reason"],
          [s["kind"] for s in r["steps"]])
```

- Actual: the first three give `ISC OR MIT`, `lexical`, `reason` `None`,
  steps `['whitespace', 'reorder']`; `\x1f` is refused (`None`,
  `unresolved`, `control or format character: U+001F`, no steps), as 0.7.0
  refuses U+001C to U+001F.
- Expected: one rule for a line or paragraph break inside a value. A vertical
  tab, a lone CR and U+2028/U+2029 are line breaks (`str.splitlines` splits on
  them), so a value holding one is two lines, as with `\n`. Refuse them like
  U+001C to U+001F, or document that they are read as a space.
- Still reproduces on 0.7.2 and 0.7.3 (same output).

### 3. `coverage` above 1 (F16)

```python
BSD1 = """Copyright (c) 2024 Example Author. All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
top = det.detect(BSD1)[0]
top["expression"], top["score"], top["coverage"]
```

- Actual: `('BSD-1-Clause', 1.0, 1.0062)`.
- Expected: `coverage` at most 1 (it is documented as a share of the licence
  text), or a documented meaning for a value above 1. Pitloom clamps it.
- Still reproduces on 0.7.2 and 0.7.3: `('BSD-1-Clause', 1.0, 1.0062)`.

### 4. Messages name a CLI flag and a networked command (F17)

```python
import os
os.environ["HOME"] = ""
LicenseDetector()                         # empty HOME
LicenseDetector("/nonexistent/licenses.db")
```

- Actual: `database: not found: no home directory; pass --db` and
  `database: not found: /nonexistent/licenses.db; run 'licenseid update'`.
  With a database built by 0.6.0, `LicenseDetector()` warns
  `database: build v2 outdated: current v3; run 'licenseid update'`.
- Expected: a library error names the library parameter (`db_path`), not the
  CLI flag `--db`. The action `run 'licenseid update'` fetches from the
  network (`compact` source); the offline fix is `licenseid update --source
  packaged`, which is what a caller with no network needs. Pitloom's own line
  says `--source packaged` next to LicenseID's `run 'licenseid update'`, so a
  user sees two different commands for one problem. Suggest naming the
  offline command, or both.
- Still reproduces on 0.7.2 and 0.7.3 (same messages, also with a 0.6.0
  database).

### 5. When a database warning is said once is undocumented (F18)

With a database built by 0.6.0:

```python
import warnings
def rec(f):
    with warnings.catch_warnings(record=True) as got:
        warnings.simplefilter("always")
        f()
    return [str(w.message) for w in got]
rec(lambda: resolve("MIT"))       # 1 warning
rec(lambda: resolve("Apache2"))   # none
rec(lambda: detect("MIT License"))  # none
rec(lambda: LicenseDetector())    # 1 warning, every construction
```

- Actual: inside `resolve()`/`detect()` a database warning is given once per
  process (`licenseid.warning.once()`, a module-level set); each
  `LicenseDetector()` gives it again. `licenseid.warning.reset_once()` clears
  the set; it is not in `__all__` and not in the README.
- Expected: document the rule (which warnings are once per process, and
  where), and make `reset_once()` (or an equivalent) a documented test hook. A
  caller that records warnings per call cannot tell "no problem" from "said
  earlier".
- Still reproduces on 0.7.2 and 0.7.3 (same warnings; `reset_once()` still
  not in `__all__`).

### 6. Deprecated ids' List names resolve to nothing

```python
for name in ["GNU Free Documentation License v1.3",
             "GNU Affero General Public License v3.0",
             "wxWindows Library License"]:
    r = resolve(name, source="packaged")
    print(name, r["expression"], r["category"], r["reason"])
```

- Actual: `None`, `unresolved`, `not found: <name>` for all 14 List names of
  deprecated ids: `Affero General Public License v1.0` (AGPL-1.0), `GNU Affero
  General Public License v3.0` (AGPL-3.0), `bzip2 and libbzip2 License
  v1.0.5` (bzip2-1.0.5), `GNU Free Documentation License v1.1`, `v1.2`,
  `v1.3` (GFDL-1.1, -1.2, -1.3), `GNU General Public License v2.0
  w/Autoconf exception`, `w/Bison exception`, `w/Classpath exception`,
  `w/Font exception`, `w/GCC Runtime Library exception`
  (GPL-2.0-with-autoconf-exception, -bison-, -classpath-, -font-,
  GPL-2.0-with-GCC-exception), `GNU General Public License v3.0 w/Autoconf
  exception`, `w/GCC Runtime Library exception`
  (GPL-3.0-with-autoconf-exception, GPL-3.0-with-GCC-exception), `wxWindows
  Library License` (wxWindows). The ids themselves resolve (`assumed_only` or
  `deprecated_ambiguous`), and a current id's name does (`MIT License` is
  `MIT`, `listed_name`).
- Expected: read the name as its deprecated id, with the same category and
  candidates the id gets (`GFDL-1.3`: `assumed_only`, candidates
  `GFDL-1.3-only`, `GFDL-1.3-or-later`); or expose the packaged List's names
  (`id -> name`) publicly. Today the only name lookup is
  `LicenseDatabase.get_license_by_name()`, which needs a database and is not
  documented, so an answer would differ with and without a database. Pitloom
  keeps the 14 names in a table until then.
- Still reproduces on 0.7.2 and 0.7.3: all 14 names give `None`, `unresolved`.

### 7. `trust: none` answers are hard to use

```python
for v in ["GPL-3.0", "GPLv3", "MIT"]:
    r = resolve(v, source="packaged")
    print(v, r["expression"], r["category"], r["trust"], r["candidates"])
```

- Actual: `GPL-3.0 assumed_only none ['GPL-3.0-only', 'GPL-3.0-or-later']`,
  the same for `GPLv3`; `MIT exact identity []`.
- Observation: an `assumed_only` answer has an expression but `trust: none`.
  A caller must special-case the category to learn that the expression is the
  author's deprecated id and not a reading LicenseID stands behind. A short
  section in the README on what to do with each `trust` value (record,
  record with a note, do not record) would remove the guesswork; or a
  boolean such as `decided` on the Resolution.
- Still reproduces on 0.7.2 and 0.7.3 (same output).

### 8. `components` is empty for most answers

```python
for v in ["MIT", "GPL-2.0+", "(MIT)", "MIT OR Apache2"]:
    print(v, resolve(v, source="packaged")["components"])
```

- Actual: `[]` for `MIT`, `GPL-2.0+`, `(MIT)` (also `MIT License`, `Apache2`,
  `GPLv3`); one entry, `py-spdx-license 0.0.1`, for `MIT OR Apache2`.
  LicenseID 0.7.0 to 0.7.2 require `py-spdx-license<0.1,>=0.0.1`.
- Expected: either the components that took part in every answer, or a
  documented rule for when the list is filled. A caller that cites the tools
  behind a reading (Pitloom writes `Tool: licenseid==0.7.1`) cannot cite the
  parser version consistently.
- Still reproduces on 0.7.2 and 0.7.3 (same output).

### 9. A `Detection` names its List, the database stays a black box (F9, remainder)

- Fixed in 0.7.0: `Detection.lists` names the List and its version
  (`source: database`).
- Open: `LicenseDatabase` has many public methods
  (`get_all_names_and_ids`, `get_deprecated_mappings`,
  `get_license_by_name`, `get_metadata`, ...) with no documentation of which
  are stable. A documented read of the database's List (version, ids, names)
  without a query would let a caller record what it detected against, and
  answer item 6 for the database case.
- Still open in 0.7.2 and 0.7.3: `__all__` and the `LicenseDatabase` methods are
  unchanged.

### 10. A non-ASCII space before "or later" is read with no step (new in 0.7.1)

```python
for v in ["GPL-2.0 or later", "MIT OR ISC"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"], [s["kind"] for s in r["steps"]])
```

- Actual (0.7.1): `'GPL-2.0 or later' GPL-2.0-or-later stated_qualifier []`;
  `'MIT OR ISC' ISC OR MIT lexical ['whitespace', 'reorder']`. On 0.7.0
  the first was refused (`qualifier stated twice`), which #158 fixed.
- Expected: the no-break space is replaced in both values, so both list a
  `whitespace` step (`from` with U+00A0, `to` with a space). With no step
  a caller that records how a value was re-spelt (Pitloom writes
  `Resolution-N` lines from `steps`) cannot say a character was changed.
- Still reproduces on 0.7.2 and 0.7.3 (same output).

### 11. Apache name variants are read inconsistently (found on 0.7.2)

```python
for v in ["Apache 2", "Apache v2", "Apache License Version 2.0",
          "Apache Version 2.0", "Apache, Version 2.0",
          "Apache Software License, Version 2.0",
          "Apache Software License 2.0", "Apache License (2.0)", "ASL 2.0"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"])
```

- Actual (0.7.2): `Apache 2` and `Apache v2` give `Apache-2.0`
  (`version_spelling`); `Apache License Version 2.0` gives `Apache-2.0`
  (`prose_form`). The other six give `None` (`unresolved`, reason
  `not found`).
- Expected: one rule for the name followed by a version. If `Apache 2` and
  `Apache v2` are `Apache-2.0`, so are `Apache Version 2.0` and
  `Apache, Version 2.0`. `Apache Software License` is the trove classifier's
  name for the licence, common in PyPI metadata, so the name with a version
  could be read too. A version in brackets and `ASL 2.0` are less clear; a
  documented refusal is fine for them.
- Pitloom keeps each refused value as licence text, with no SPDX id.
- Fixed in 0.7.3 (#172): all eight name-and-version spellings give
  `Apache-2.0`: `Apache 2` and `Apache v2` (`version_spelling`), the other
  six (`prose_form`), so Pitloom records each as `Apache-2.0`. `ASL 2.0`
  stays `None` (`unresolved`, `not found: ASL 2.0`), a refusal 0.7.3's
  CHANGELOG documents, as the expected result allows. Drop this item from
  the issue.

## Not in the issue

The earlier draft's nine findings are findings 1 to 9 above; the current
text adds finding 10, the 0.7.1 version references, the 0.7.2 and 0.7.3
status of each finding, and finding 11 (found on 0.7.2, fixed in 0.7.3).

0.7.2's new warning `input: too few words for text: <reason>` (#161) is no
finding: it says why a short text gets no match. Pitloom relays it as a
`WARNING:` line for a licence text of under ten words, which fails seven
Pitloom tests on 0.7.2; the relay level is Pitloom's to settle. Settled in
#455: no licence in a short text is absent data, relayed at `DEBUG`.

---

Reproducers 1 to 11 re-run 2026-11-07 on LicenseID 0.7.1, 0.7.2 and 0.7.3
(PyPI wheels, CPython 3.10.20, fresh `HOME`, `licenseid update --source
packaged`; 4 and 5 also with a database built by 0.6.0): the output above,
and on 0.7.2 and 0.7.3 the line each finding gives for it. 0.7.3 differs
from 0.7.2 only in item 11.
