---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# LicenseID handoff: licence families and the relation between two licences

See also: [upstream-issues.md](upstream-issues.md) (the other asks),
[../../design/licenseid-handoff.md](../../design/licenseid-handoff.md)
(the first handoff), and the open ledger entry "A G2 conflict where a
generic licence name narrows to its file's licence" in
[known-bugs/licences-and-licenseid.md](../../design/known-bugs/licences-and-licenseid.md).

Written 2026-11-28 from Pitloom PR #569 (head 778a96c5). Every "today"
claim was checked by running LicenseID 0.9.4. Do not edit Pitloom.

## Why in LicenseID

The family data belongs in LicenseID, so that Pitloom, and any other
licence processor, does not have to keep its own table of which licences
a classifier covers. Treat `in_family()`, `family_of()` and `relation()`
as a general LicenseID feature for every consumer, not a Pitloom special
case. Pitloom keeps no copy of that data.

## Use case

A tool compares a package's stated licence (a `License ::` trove
classifier, or a free-text `License` header) with the SPDX id detected
from its licence file. There are four relations between the two:

| Relation | Example (stated -> detected) | Conflict? |
| - | - | - |
| same | a header holding the MIT body -> `MIT` | no |
| narrowing | `BSD License` -> `BSD-3-Clause`; `Apache Software License` -> `Apache-2.0`; `Python Software Foundation License` -> `PSF-2.0` | no, but worth recording |
| widening | `LGPL-3.0-only` -> `LGPL-3.0-or-later` (the file grants more) | yes |
| disagree | `Apache Software License` -> `MIT` | yes |

"Same" already works today: `read_license_text` reads a whole body as the
id, and Pitloom #569 uses it. "Narrowing" is what needs LicenseID.

## Scope

- **In scope: trove classifiers.** PyPI's classifier list is closed and
  versioned, so a table saying "classifier X covers ids {...}" is
  grounded data, not a guess. `licenseid.trovenames` is the natural home.
- **Out of scope for the table: free-text short names** in a `License`
  header (`BSD`, `Expat license`, `PSFL`). Does LicenseID want to read
  those at all? In the data below, each of those packages also carries a
  classifier that answers the question.

## What `trovenames` exposes today (0.9.4)

- `TROVE_NAMES`: a dict of 89 classifier names to `TroveEntry(ids,
  reading, osi)`, with `reading` one of `stated` (49), `assumed` (5) or
  `none` (35).
- `TROVE_CLASSIFIERS_VERSION`: `"2026.9.21.13"`.
- `strip_trove_path(text)`: `"License :: OSI Approved :: BSD License"`
  gives `"BSD License"`.
- `BSD License`, `Apache Software License` and `Python Software
  Foundation License` are `TroveEntry(ids=(), reading='none',
  osi=True)`. The module docstring says the last two "imply ``Apache-2.0``
  and ``PSF-2.0`` by usage, not by what they write (reading by usage is
  deferred)". Other `none` names include `GNU General Public License
  (GPL)`, `GNU Library or Lesser General Public License (LGPL)`,
  `Artistic License`, `Zope Public License` and `zlib/libpng License`.
- For contrast: `MIT License` is `(('MIT',), 'stated')`; `GNU Lesser
  General Public License v3 (LGPLv3)` is `(('LGPL-3.0',), 'assumed')`.
- `licenseid.resolve(name)` gives `expression=None`,
  `category='unresolved'` and `reason='not found: <name>'` for `Apache
  Software License`, `BSD License`, `BSD`, `Expat license`, `PSFL` and
  `Python Software Foundation License`.

## Data: Pitloom's own environment

There are 15 packages whose metadata names no SPDX licence, with a
licence file read. For each: what was stated and where, its classifier,
and the id detected from the file.

| Package | Stated (field) | `License ::` classifier | Detected | Relation |
| - | - | - | - | - |
| html5rdf 1.2.1 | MIT body (header) | MIT License | MIT | same (done) |
| isodate 0.7.2 | BSD-3 body (header) | BSD License | BSD-3-Clause | same (done) |
| pyshacl 0.40.2 | Apache 2.0 body (header) | Apache Software License | Apache-2.0 | same (done) |
| fickling 0.1.12 | LGPL 3 body (header) | ... v3 or later (LGPLv3+) | LGPL-3.0-or-later | same (done; the classifier breaks the tie) |
| jinja2 3.1.6 | `BSD License` (classifier) | BSD License | BSD-3-Clause | narrowing |
| colorama 0.4.6 | `BSD License` (classifier) | BSD License | BSD-3-Clause | narrowing |
| safetensors 0.8.0 | `Apache Software License` (classifier) | Apache Software License | Apache-2.0 | narrowing |
| trove-classifiers 2026.9.21.13 | `Apache Software License` (classifier) | Apache Software License | Apache-2.0 | narrowing |
| ghp-import 2.1.0 | `Apache Software License` (header) | Apache Software License | Apache-2.0 | narrowing by its classifier |
| mpmath 1.3.0 | `BSD` (header) | BSD License | BSD-3-Clause | narrowing by its classifier |
| nodeenv 1.12.0 | `BSD` (header) | BSD License | BSD-3-Clause | narrowing by its classifier |
| semantic-version 2.10.0 | `BSD` (header) | BSD License | BSD-2-Clause | narrowing by its classifier |
| defusedxml 0.7.1 | `PSFL` (header) | Python Software Foundation License | PSF-2.0 | narrowing by its classifier |
| mccabe 0.7.0 | `Expat license` (header) | MIT License | MIT | same by its classifier (`stated` MIT) |
| python-dateutil 3.0.0 | `Dual License` (header) | BSD License + Apache Software License | not compared | the file is not read: several licences |

There are no widening and no disagree cases in this environment. The
classifiers alone settle every short header name.

## API asked for

Minimal: either primitive lets a consumer work out narrowing itself (the
same family, the stated value generic, the detected one specific):

```python
licenseid.in_family(licence: str, family: str) -> bool | None
# in_family("BSD-3-Clause", "BSD License") -> True
# in_family("MIT", "Apache Software License") -> False
# None for a family LicenseID does not know

licenseid.family_of(licence: str) -> str | None
# family_of("BSD-3-Clause") -> "BSD"; family_of("Apache-2.0") -> "Apache"
# also takes a trove classifier name: family_of("BSD License") -> "BSD"
```

Richer, optional:

```python
licenseid.relation(stated: str, detected_id: str) -> Relation
# "same" | "narrowing" | "widening" | "disagree" | "unknown",
# plus the basis (trove table release, rule) for the record
```

The examples above are the desired answers. None of these functions
exists in 0.9.4.

## To decide in LicenseID

1. How are families named (`BSD`, `Apache`, or the classifier name)?
2. Can a licence belong to more than one family (for example `MIT-0`, or
   `0BSD` and BSD)?
3. Where does the family data come from: the trove classifier list, the
   SPDX License List, or LicenseID's own table? Does it follow PyPI's
   classifier releases (`TROVE_CLASSIFIERS_VERSION`)?
4. How does a licence with no family answer: `None`, or a family of its
   own?
5. How do `-only` and `-or-later`, and `AND`/`OR` expressions, map onto
   narrowing and widening? Is `GPL-3.0-only` stated against
   `GPL-3.0-or-later` detected widening? Is `MIT` stated against
   `MIT OR Apache-2.0` detected widening? Is `BSD License` stated against
   `BSD-3-Clause AND MIT` detected anything?
6. Should free-text short names (`BSD`, `Expat license`, `PSFL`) be read
   at all, or only classifiers?
7. How should narrowing be reported, so a consumer can record it? On the
   Pitloom side that might be a `Relation: narrowing` provenance note
   instead of a conflict annotation; that is not decided.
