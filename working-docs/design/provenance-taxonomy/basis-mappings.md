---
Created: 2026-11-28
Last-Modified: 2026-11-28
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Basis: mappings to other vocabularies (loose)

See also: [basis.md](basis.md) (the values and their rules; this part
was moved out of it on 2026-11-28, unchanged, for the size of the
page), [alignment.md](alignment.md),
[vocabularies-considered.md](vocabularies-considered.md).

SSN/SOSA (W3C Recommendation, 2017) describes the observed half: an
`sosa:Observation` is an act of carrying out a `sosa:Procedure` to "estimate
or calculate a value of a property" of a `sosa:FeatureOfInterest`, made by a
`sosa:Sensor` (a device, an agent or software). It has no class for a
value that is stated and not observed; its one mention is an example under
`sosa:ObservableProperty`, where the value of a classic car "is not
(directly) observable but asserted". Terms and quotes checked against the
Recommendation, 2026-11-16. A 2023 Edition is a Working Draft: it moves
`Stimulus` and `isProxyFor` to the `sosa:` namespace, drops the
`ssn-system:` namespace with `Accuracy` and `MeasurementRange`, and drops
the classic car example.

| Value | SSN/SOSA | SPDX 3 | CISA 2026 | CycloneDX | ECO |
| --- | --- | --- | --- | --- | --- |
| `declared` | "asserted"; no class | - | - | `technique: attestation`, `manifest-analysis` | `ECO:0000204` author statement |
| `measured` | `sosa:Observation` | `completeness: complete` on the relationship that carries the fact | - | `hash-comparison`, `binary-analysis`, `confidence: 1` | `ECO:0007669` computational evidence used in automatic assertion |
| `detected` | `sosa:Observation`, by any `sosa:Sensor`; for a best match, `ssn-system:Accuracy` below the full | - | - | `technique` with `confidence` below 1 | `ECO:0000041` similarity evidence (the best-match case) |
| `inferred` | no class; `ssn:isProxyFor` is related only (see below) | - | - | `technique: other` | `ECO:0000363` computational inference used in automatic assertion |
| `lower-bound` | a value beyond `ssn-system:MeasurementRange` | `completeness: incomplete` | - | - | - |
| `not-measured` | no observation made | `completeness: noAssertion`; `NoAssertionElement` | unknown | - | - |

The proxy test of this page is this model's own. `ssn:isProxyFor` relates
a stimulus to the property it stands for, and in SSN every stimulus does:
its example is a thermometer ("the expansion of quicksilver is a stimulus
that serves as a proxy for some temperature property"). So SSN's proxy
does not mark `inferred`; the word is shared, the line is not (corrected
2026-11-16, after a fact-check).

SOSA aligns itself to PROV-O in a non-normative module (Observation to
`prov:Activity`, Sensor to `prov:Agent` and `prov:Entity`, Procedure to
`prov:Plan`, Result to `prov:Entity`), which is the bridge from this model
to PROV for a single value. PROV-O itself has no word for a basis: it
tells `declared` (the asserter's own act is not known) from `measured`,
`detected` and `inferred` (it is known). The lines between those three
are this model's own: SOSA has one class for every observation, and SSN's
proxy marks none of them (above). SIO has loose matches for three
values: `statement` for `declared`, `measurement value` for a `measured`
quantity, `conclusion` ("reached
after considering the evidence, arguments or premises") for `inferred`.
Its `hypothesis` ("a proposed explanation for a phenomenon") is not
`inferred`: an inferred value explains nothing. The pattern:
[alignment.md](alignment.md).

SPDX has no property for the basis of a value; it stays in the
Annotation, and the gap is FG-13 (with FG-10 for a declared hash) in
[sbom-format-gaps.md](../sbom-format-gaps.md).
