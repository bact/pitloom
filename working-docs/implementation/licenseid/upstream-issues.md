---
Created: 2026-11-06
Last-Modified: 2026-11-08
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# LicenseID upstream issues

See also: [adoption-built.md](adoption-built.md)
(how Pitloom adopted LicenseID).

Findings from the Pitloom adoption of LicenseID, kept so they are not lost.

- **Status:** drafted, not yet filed upstream.
- **Where to file:** the LicenseID repository, as one issue.
- **Who files:** the maintainer.
- **Pitloom dependency:** Pitloom 0.23.4 requires `licenseid>=0.8.2,<0.9`.

## Index of findings

Severity: **contract** = behaviour a caller cannot rely on or that
contradicts the documented meaning; **process** = missing documentation or
a hook; **edge** = unusual input.

| # | Finding | Severity | Pitloom workaround | Status |
| - | - | - | - | - |
| 1 | Short word detected as a licence | contract | none | fixed in LicenseID 0.7.2 |
| 2 | Which characters are white space | edge/doc | none | reproduces on 0.8.2 |
| 3 | `coverage` above 1 | contract | Pitloom clamps it | reproduces on 0.8.2 |
| 4 | Messages name `--db` and a networked command | process | own line names `--source packaged` | reproduces on 0.8.2 |
| 5 | When a database warning is said once | process | none | reproduces on 0.8.2 |
| 6 | Deprecated ids' List names resolve to nothing | contract | 14 names in `_license_names.py` `UNREAD_LISTED_NAMES` | reproduces on 0.8.2 |
| 7 | `trust: none` answers are hard to use | process | special-cases the category | reproduces on 0.8.2 |
| 8 | `components` empty for most answers | contract | none | reproduces on 0.8.2 |
| 9 | Database is a black box | process | none | still open on 0.8.2 |
| 10 | Non-ASCII space before "or later" has no step | contract | none | reproduces on 0.8.2 |
| 11 | Apache name variants read inconsistently | edge | none needed | fixed in LicenseID 0.7.3 |

The reproducers were re-run on LicenseID 0.8.2 (PyPI wheel, fresh `HOME`,
`licenseid update --source packaged`) on 2026-11-08, with the same results as
on 0.8.1; item 5 used a database built by LicenseID 0.6.0. Item 9 is open:
`LicenseDatabase` is public, in `__all__`, has 15 public methods, and its
stability is undocumented.

## Issue text

The text below is ready to paste. Headings are one level lower than in the
issue.

## LicenseID: findings from the Pitloom adoption

Each reproducer reads the packaged SPDX License List (3.29.0). Items 1 and 11
are fixed and are not part of the issue. Common setup:

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

- Fixed in LicenseID 0.7.2 (#161). Drop this item from the issue.

### 2. Which characters count as white space (F15, remainder)

```python
for v in ["MIT\x0bOR ISC", "MIT\rOR ISC", "MIT\u2028OR ISC", "MIT\x1fOR ISC"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"], r["reason"],
          [s["kind"] for s in r["steps"]])
```

- Actual: the first three give `ISC OR MIT`, `lexical`, `reason` `None`,
  steps `['whitespace', 'reorder']`; `\x1f` is refused (`None`,
  `unresolved`, `control or format character: U+001F`, no steps), as U+001C to
  U+001F are.
- Question, not a defect: probably intentional (to confirm)
  (a lenient reading of a wrapped value, recorded as `whitespace` steps;
  0.8.1 also normalises invisible spaces and trims control characters). Is
  this deliberate? Please document which characters count as white space;
  `\x1f` is refused while the others are read.

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

- Actual (reproduces on 0.8.2): `('BSD-1-Clause', 1.0, 1.0062)`.
- Expected: `coverage` at most 1 (it is documented as a share of the licence
  text), or a documented meaning for a value above 1. Pitloom clamps it.

### 4. Messages name a CLI flag and a networked command (F17)

```python
import os
os.environ["HOME"] = ""
LicenseDetector()                         # empty HOME
LicenseDetector("/nonexistent/licenses.db")
```

- Actual: `database: not found: no home directory; pass --db` and
  `database: not found: /nonexistent/licenses.db; run 'licenseid update'`
  (both reproduce on 0.8.2). With a database of an older build,
  `LicenseDetector()` warns
  `database: build v2 outdated: current v4; run 'licenseid update'`.
- Expected: a library error names the library parameter (`db_path`), not the
  CLI flag `--db`. The action `run 'licenseid update'` fetches from the
  network (`compact` source); the offline fix is `licenseid update --source
  packaged`, which is what a caller with no network needs. Pitloom's own line
  says `--source packaged` next to LicenseID's `run 'licenseid update'`, so a
  user sees two different commands for one problem. Suggest naming the
  offline command, or both.

### 5. When a database warning is said once is undocumented (F18)

With a database of an older build:

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

- Actual (0.6.0-built database, on 0.8.2): `resolve("MIT")` warns once,
  `database: build v2 outdated: current v4; run 'licenseid update'`;
  `resolve("Apache2")` and `detect("MIT License")` give none; each
  `LicenseDetector()` warns again. A database built by 0.8.1 or 0.8.2 gives
  no warning. Inside `resolve()`/`detect()` a database warning is given once
  per process (`licenseid.warning.once()`, a module-level set); each
  `LicenseDetector()` gives it again. `licenseid.warning.reset_once()` clears
  the set; it is still not in `__all__` and not in the README.
- Expected: document the rule (which warnings are once per process, and
  where), and make `reset_once()` (or an equivalent) a documented test hook. A
  caller that records warnings per call cannot tell "no problem" from "said
  earlier".

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

### 7. `trust: none` answers are hard to use

```python
for v in ["GPL-3.0", "GPLv3", "MIT"]:
    r = resolve(v, source="packaged")
    print(v, r["expression"], r["category"], r["trust"], r["candidates"])
```

- Actual (reproduces on 0.8.2): `GPL-3.0 assumed_only none ['GPL-3.0-only',
  'GPL-3.0-or-later']`, the same for `GPLv3`; `MIT exact identity []`. The
  result has no `decided` key.
- Observation: an `assumed_only` answer has an expression but `trust: none`.
  A caller must special-case the category to learn that the expression is the
  author's deprecated id and not a reading LicenseID stands behind. A short
  section in the README on what to do with each `trust` value (record,
  record with a note, do not record) would remove the guesswork; or a
  boolean such as `decided` on the Resolution.

### 8. `components` is empty for most answers

```python
for v in ["MIT", "GPL-2.0+", "(MIT)", "MIT OR Apache2"]:
    print(v, resolve(v, source="packaged")["components"])
```

- Actual (reproduces on 0.8.2): `[]` for `MIT`, `GPL-2.0+`, `(MIT)` (also
  `MIT License`, `Apache2`, `GPLv3`); one entry, `py-spdx-license 0.0.1`, for
  `MIT OR Apache2`.
  LicenseID requires `py-spdx-license<0.1,>=0.0.1`.
- Expected: either the components that took part in every answer, or a
  documented rule for when the list is filled. A caller that cites the tools
  behind a reading (Pitloom writes `Tool: licenseid==<version>`) cannot cite the
  parser version consistently.

### 9. A `Detection` names its List, the database stays a black box (F9, remainder)

- `Detection.lists` names the List and its version (`source: database`).
- Open on 0.8.2: `LicenseDatabase` is public and in `__all__`, with 15
  public methods
  (`get_all_names_and_ids`, `get_deprecated_mappings`,
  `get_license_by_name`, `get_metadata`, ...) and no documentation of which
  are stable. A documented read of the database's List (version, ids, names)
  without a query would let a caller record what it detected against, and
  answer item 6 for the database case.

### 10. A non-ASCII space before "or later" is read with no step

```python
for v in ["GPL-2.0 or later", "MIT OR ISC"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"], [s["kind"] for s in r["steps"]])
```

- Actual: `'GPL-2.0 or later' GPL-2.0-or-later stated_qualifier []`;
  `'MIT OR ISC' ISC OR MIT lexical ['whitespace', 'reorder']`.
- Expected: the no-break space is replaced in both values, so both list a
  `whitespace` step (`from` with U+00A0, `to` with a space). With no step
  a caller that records how a value was re-spelt (Pitloom writes
  `Resolution-N` lines from `steps`) cannot say a character was changed.

### 11. Apache name variants are read inconsistently

```python
for v in ["Apache 2", "Apache v2", "Apache License Version 2.0",
          "Apache Version 2.0", "Apache, Version 2.0",
          "Apache Software License, Version 2.0",
          "Apache Software License 2.0", "Apache License (2.0)", "ASL 2.0"]:
    r = resolve(v, source="packaged")
    print(repr(v), r["expression"], r["category"])
```

- Fixed in LicenseID 0.7.3 (#172): all eight name-and-version spellings give
  `Apache-2.0`; `ASL 2.0` stays `None` (`unresolved`), a documented refusal.
  Drop this item from the issue.

## Not in the issue

LicenseID's warning `input: too few words for text: <reason>` (#161) is no
finding: it says why a short text gets no match. Pitloom relays no licence in
a short text as absent data, at `DEBUG` (#455).
