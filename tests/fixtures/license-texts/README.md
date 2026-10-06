---
Last-Modified: 2026-10-05
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence text fixtures

See also: [../real-world-projects/README.md](../real-world-projects/README.md)
(the PyYAML and requests sdists, the other two licence regressions);
[`../../assemble/test_license_detection_corpus.py`](../../assemble/test_license_detection_corpus.py)
for the test that reads them.

Real `LICENSE` files, byte for byte as installed (`.dist-info/licenses/`),
each one a case `licenseid` alone ranks wrong or misses (a near-variant
licence scored above the verbatim one, a licence hidden behind its
copyright notice), or a near-tie the rules must not drop (a GPL text
scores `-only` and `-or-later` alike). Each file is the package's own
licence, kept with its notice. `.gitattributes` marks the `*-LICENSE` files `-text`, so a Windows checkout
keeps the bytes.

`expected.json`, one entry per file:

| Key | Meaning |
| --- | --- |
| `source` | Package and member it was copied from |
| `license` | The licence the package states |
| `stated` | `detect_license_from_text(text, stated=license)` |
| `unstated` | `detect_license_from_text(text)`: the licence (or its `-only`/`-or-later` sibling: a GPL text cannot tell), or `null` for a near-tie |
| `note` | What `licenseid` gives on its own |

The expectations hold for `licenseid` 0.3.7 and 0.4.0 and their databases. A newer
`licenseid` may score them differently: a changed `unstated` from `null` to
the licence is an improvement; any other licence is a regression.
