---
Created: 2026-10-03
Last-Modified: 2026-10-03
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: remote and installed metadata

See also: [README.md](README.md) (index of these notes),
[spdx-modelling.md](spdx-modelling.md),
[identity-and-archives.md](identity-and-archives.md),
[license-pipeline.md](../license-pipeline.md),
[remote-source-ingestion.md](../../design/remote-source-ingestion.md).

What core metadata and PyPI-style sources actually contain, measured on
installed distributions and live fetches.

- **`email.utils.parseaddr` loses a whole address list.** A
  `Maintainer-email` such as `"Alice <a@x.org>, Bob <b@x.org>"`
  (pipdeptree has 3 maintainers) gives `('', '')`: every address is lost,
  not only the extras. Same on 3.8.20 to 3.14.3. `getaddresses([s])`
  returns both pairs (#131).
  Do: parse core-metadata author and maintainer email fields with
  `getaddresses`.
- **`http.client.IncompleteRead` is not an `OSError`.** Its MRO is
  `IncompleteRead`, `HTTPException`, `Exception`, so a truncated PyPI JSON
  response escapes `except (URLError, OSError, ValueError)` and aborts the
  whole SBOM build (3.10 and 3.14) (#131).
  Do: add `http.client.HTTPException` to every network-fetch `except`.
- **The legacy `License` field is not an SPDX expression.** numpy 2.2.6
  (Metadata 2.1) carries 48,569 characters over 971 lines in `License`
  and no `License-Expression`; requests 2.34.2 (Metadata 2.4) has free
  text `"Apache 2.0"` and no `License-Expression`; packaging 26.3, h5py
  3.16.0 and onnx 1.22.0 carry a `License-Expression`. Pitloom records a
  licence from installed metadata as `hasConcludedLicense`, not declared,
  since installed metadata is not a transparent source; #131 fixed a bug
  that discarded that relationship.
  Do: prefer `License-Expression`, treat `License` as unverified text, and
  never emit it as a declared expression.
- **PyPI purl shape.** The name goes through `canonicalize_name`, and a
  local-version `+` is percent-encoded: `Demo_Pkg 1.0+local.1` becomes
  `pkg:pypi/demo-pkg@1.0%2Blocal.1`. A dependency with no known version
  gets a name-only `pkg:pypi/<name>`, which purl allows; the main package
  gets none (#131).
  Do: canonicalise the purl name, encode `+`, and emit a name-only purl
  rather than none.
