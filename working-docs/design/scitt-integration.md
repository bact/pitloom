---
Created: 2026-08-30
Last-Modified: 2026-08-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# IETF SCITT integration

See also: [roadmap.md](roadmap.md) (Long-term -- "IETF SCITT
integration").

Submit a generated SBOM as a signed SCITT statement to a transparency
service, receive a receipt back as proof of registration; separately,
verify a dependency's own SCITT receipt when consuming its SBOM and
feed the result into the existing provenance role vocabulary
(`externalReported` vs `sbomAuthorSupplied`). See <https://scitt.io/>.

Complementary to (not a replacement for) the PEP 740 attestations item
(roadmap Long-term) -- SCITT covers third-party transparency-log
attestation, PEP 740 covers index-hosted signing. Related: [Issue #79](https://github.com/bact/pitloom/issues/79)
(Cisco `model-provenance-kit`) could layer on the same mechanism.

## Receipt placement

Decided 2026-08-30: outside the wheel, not in `.dist-info/sboms/`. A
receipt embeds a transparency-log timestamp/index that varies per
submission, so embedding it would break wheel/SBOM reproducibility;
obtaining it also requires a network call to an external service,
which a build hook shouldn't block on. Sidecar file next to the built
wheel (e.g. `dist/<wheel>.receipt.cbor`), produced by a separate
post-build step (`loom scitt submit`) -- mirrors how PEP 740 itself
keeps attestations outside the artifact, served by the index rather
than embedded.

## Pitloom's role is client-only, not log operator

A receipt is countersigned by the transparency service itself -- only
the log can issue one. Pitloom builds and signs the SCITT statement,
submits it to a transparency-service URL the user configures
(self-hosted CCF instance, DataTrails, etc.), and stores whatever
receipt comes back; it never runs a transparency service of its own.

## Tooling landscape

Checked 2026-08-30, thin: DataTrails is the main hosted,
spec-compliant (draft-10) transparency service, with a GitHub Action
client but no general Python library; the reference client/server,
`scitt-api-emulator` (Python), is archived and unmaintained since
2024-11-22. No mature OSS client library exists yet, so this needs a
from-scratch thin client -- `pyproject.toml` has no signing/crypto
dependency today (`pycose` or `cryptography` would be new).

## Shape

```
loom scitt submit dist/mypkg-1.0.0.whl
  1. hash the SBOM, build a COSE_Sign1 statement
     (issuer identity + sha256(sbom) payload)
  2. sign it with the user's configured key
  3. POST to the configured transparency-service URL
  4. save the returned receipt as
     dist/mypkg-1.0.0.whl.receipt.cbor

loom scitt verify <dependency-sbom> --receipt <file>
  -- checks a third party's receipt when consuming their SBOM
     as a dependency
```
