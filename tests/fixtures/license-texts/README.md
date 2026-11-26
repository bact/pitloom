---
Last-Modified: 2026-11-26
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
each one a case LicenseID alone ranks wrong or misses (a near-variant
licence scored above the verbatim one, a licence hidden behind its
copyright notice), or a near-tie the rules must not drop (a GPL text
scores `-only` and `-or-later` alike). Each file is the package's own
licence, kept with its notice. `.gitattributes` marks
the `*-LICENSE` files `-text`, so a Windows checkout keeps the bytes, and
`.editorconfig` exempts them, so an editor keeps them too.

`expected.json`, one entry per file:

| Key | Meaning |
| --- | --- |
| `source` | Package and member it was copied from |
| `license` | The licence the package states |
| `stated` | `detect_license_from_text(text, stated=license)` |
| `unstated` | `detect_license_from_text(text)`: the licence (or its `-only`/`-or-later` sibling: a GPL text cannot tell), or `null` for a near-tie |
| `note` | What LicenseID gives on its own |

The expectations and notes hold for LicenseID 0.4.1 and 0.4.2 and
their SPDX License List 3.29.0 database (0.4 caps a score at 1).
A newer LicenseID may score them differently: a changed `unstated` from
`null` to the licence is an improvement; any other licence is a regression.

Two files hold the texts of several licences, and no licence is detected
from either, stated or not (`test_a_file_of_several_licence_texts_gives_no_licence`;
LicenseID 0.9.3 lists their texts in `Detection.texts`):

| File | Copied from | Texts it holds |
| --- | --- | --- |
| `numpy-2.5.5-LICENSE` | `numpy-2.5.5.dist-info/licenses/LICENSE.txt` | BSD-3-Clause, BSD-3-Clause-Open-MPI, GPL-3.0 (LicenseID alone: `GPL-3.0-only`) |
| `types-setuptools-84.2.0.20261122-LICENSE` | `types_setuptools-84.2.0.20261122.dist-info/licenses/LICENSE` | Apache-2.0, MIT (LicenseID alone: `Apache-2.0`) |
