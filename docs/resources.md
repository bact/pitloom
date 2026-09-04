---
Created: 2026-03-26
Last-Modified: 2026-09-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Resources

## Python Enhancement Proposals (PEPs)

> Note: PEPs are historical document.
> The up-to-date, canonical spec for Python packaging,
> is maintained on the
> [PyPA specs page](https://packaging.python.org/en/latest/specifications/).

PEPs Pitloom's extractors and assemblers directly implement support for,
each with a short note on what SBOM metadata it feeds:

- [PEP 376][pep-376] – Database of Installed Python Distributions:
  `RECORD` hash/size format, reused for wheel-embedded SBOM file digests
  (see PEP 770 below).
- [PEP 427][pep-427] – The Wheel Binary Package Format 1.0: defines the
  `.dist-info/` layout Pitloom reads/writes package files against.
  **Stale on one point** the PEP text itself doesn't reflect: the
  name/version escaping rule for `.dist-info` directory naming (PEP 503
  normalization, then `-` → `_`) was *revised in 2021* to match real
  tooling — see the canonical
  [Binary Distribution Format spec][pep-427-spec] instead of this PEP
  for that rule specifically.
- [PEP 440][pep-440] – Version Identification and Dependency
  Specification: version syntax used for dependency-constraint
  conversion (e.g. Poetry's `^`/`~`) and wheel-vs-SBOM version checks.
- [PEP 503][pep-503] – Simple Repository API: package-name
  normalization, used generically wherever two package names must
  compare equal regardless of case/`-`/`_`/`.` -- PyPI purl
  construction, dependency dedup, wheel-vs-SBOM name checks, and wheel
  `.dist-info` path escaping.
- [PEP 508][pep-508] – Dependency specification for Python Software
  Packages: parsed for each dependency's name, version constraints,
  extras, and markers.
- [PEP 517][pep-517] – A build-system independent format for source
  trees: build-backend interface used to detect which backend produced
  a project's metadata.
- [PEP 518][pep-518] – Specifying Minimum Build System Requirements for
  Python Projects: `[build-system]` table read to select the right
  metadata/file-discovery backend.
- [PEP 621][pep-621] – Storing project metadata in pyproject.toml:
  primary source of name, version, authors, dependencies, license,
  urls, etc.
- [PEP 639][pep-639] – Improving License Clarity with Better Package
  Metadata: SPDX license expression and `license-files` bundling → the
  SBOM's declared-license and license-file elements.
- [PEP 770][pep-770] – Improving measurability of Python packages with
  Software Bill-of-Materials: defines `.dist-info/sboms/`, where
  Pitloom embeds/locates a wheel's own SBOM.
- [All Packaging PEPs][packaging-peps]

[pep-376]: https://peps.python.org/pep-0376/
[pep-427]: https://peps.python.org/pep-0427/
[pep-427-spec]: https://packaging.python.org/en/latest/specifications/binary-distribution-format/#escaping-and-unicode
[pep-440]: https://peps.python.org/pep-0440/
[pep-503]: https://peps.python.org/pep-0503/
[pep-508]: https://peps.python.org/pep-0508/
[pep-517]: https://peps.python.org/pep-0517/
[pep-518]: https://peps.python.org/pep-0518/
[pep-621]: https://peps.python.org/pep-0621/
[pep-639]: https://peps.python.org/pep-0639/
[pep-770]: https://peps.python.org/pep-0770/
[packaging-peps]: https://peps.python.org/topic/packaging/

## SBOM resources

- SBOM-Everywhere:
  <https://sbom-catalog.openssf.org/>
  Guides and best practices for SBOM in open source projects.
- OpenChain SBOM Document Quality Guide Compliance Management Guide for
  the Supply Chain version 1.0.0:
  <https://docs.google.com/document/d/1iuXX8j10N70dfce1-CZFWhW6S2jEqc--flcCgXMMdjg/edit?usp=sharing>
- 2026 Minimum Elements for a Software Bill of Materials (SBOM):
  <https://www.cisa.gov/resources-tools/resources/2026-minimum-elements-software-bill-materials-sbom>
  <https://www.cisa.gov/sites/default/files/2026-07/2026_cisa_sbom_minimum_elements_508c.pdf>
- BSI TR-03183-2: Cyber Resilience Requirements for Manufacturers and
  Products - Part 2: Software Bill of Materials (SBOM) Version 2.1.0
  <https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/TechGuidelines/TR03183/BSI-TR-03183-2_v2_1_0.pdf?__blob=publicationFile&v=5>
- OpenChain AI SBOM Compliance Management Guide for the Supply Chain version 1.0:
  <https://github.com/OpenChain-Project/Reference-Material/blob/master/AI-SBOM-Compliance/en/Artificial-Intelligence-System-Bill-of-Materials-Compliance-Management-Guide.md>
- The State of Software Bill of Materials (SBOM) and Cybersecurity Readiness:
  <https://www.linuxfoundation.org/research/the-state-of-software-bill-of-materials-sbom-and-cybersecurity-readiness>
- SBOMs in the Era of the CRA: Toward a Unified and Actionable Framework:
  <https://openssf.org/blog/2025/10/22/sboms-in-the-era-of-the-cra-toward-a-unified-and-actionable-framework/>
- Challenges Facing the Security of the Software Supply Chain:
  <https://linuxfoundation.eu/newsroom/the-state-of-the-secure-software-supply-chain>
- Building an Open AIBOM Standard in the Wild:
  <https://arxiv.org/abs/2510.07070> (design notes on SPDX 3.0 AI profile)
- What We Know about AIBOMs: Results from a Multivocal Literature Review on
  Artificial Intelligence Bill of Materials:
  <https://dl.acm.org/doi/10.1145/3786773>
- AIBoMGen: Generating an AI Bill of Materials for Secure, Transparent,
  and Compliant Model Training
  <https://arxiv.org/abs/2601.05703>
- An Empirical Study on Software Bill of Materials: Where We Stand and
  the Road Ahead:
  <https://arxiv.org/abs/2301.05362>
- A shared G7 vision on software bill of materials for AI: Transparency and
  Cybersecurity along the AI supply chain:
  <https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/KI/SBOM-for-AI_Food-for-thoughts.html>
- G7 Software Bill of Materials (SBOM) for Artificial Intelligence - Minimum Elements
  <https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/KI/SBOM-for-AI_minimum-elements.html>
- BOMs Away! Inside the Minds of Stakeholders: A Comprehensive Study of Bills
  of Materials for Software Systems:
  <https://arxiv.org/abs/2309.12206>
- A Landscape Study of Open-Source Tools for Software Bill of Materials (SBOM)
  and Supply Chain Security:
  <https://arxiv.org/abs/2402.11151>

## AI documentation resources

- AIDOC-AP: An Application Profile for Technical Documentation of AI Systems:
  <https://www.semantic-web-journal.net/system/files/swj4042.pdf>
  <https://github.com/CERTAIN-Project/aidoc-ap>
  <https://certain-project.github.io/aidoc-ap/>
- TechOps: Technical Documentation Templates for the AI Act:
  <https://arxiv.org/abs/2508.08804>
- AICat: An AI Cataloguing Approach to Support the EU AI Act:
  <https://arxiv.org/abs/2501.04014>

## SPDX resources

- SPDX project: <https://spdx.dev/>
- SPDX 3.0 spec: <https://spdx.github.io/spdx-spec/v3.0/>
  - Model: <https://spdx.org/rdf/3.0/spdx-model.ttl>
  - JSON Schema: <https://spdx.org/schema/3.0/spdx-json-schema.json>
  - JSON-LD context: <https://spdx.org/rdf/3.0/spdx-context.jsonld>
  - JSON-LD serialization annotation: <https://spdx.org/rdf/3.0/spdx-json-serialize-annotations.ttl>
- SPDX 3.1 spec (under development): <https://spdx.github.io/spdx-spec/v3.1-dev/>
  - Terms: <https://spdx.github.io/spdx-spec/v3.1-dev/terms-and-definitions/>
  - Model: <https://spdx.org/rdf/3.1/spdx-model.ttl>
  - JSON Schema: <https://spdx.org/schema/3.1/spdx-json-schema.json>
  - JSON-LD context: <https://spdx.org/rdf/3.1/spdx-context.jsonld>
  - JSON-LD serialization annotation: <https://spdx.org/rdf/3.1/spdx-json-serialize-annotations.ttl>
- SPDX 3 JSON validation guide: <https://github.com/spdx/spdx-3-model/blob/develop/serialization/jsonld/validation.md>
- SPDX 3 model Python binding: <https://github.com/spdx/spdx-python-model>
- SPDX 3 model format and style guide (useful when reading model source files
  from spdx-3-model repo):
  <https://github.com/spdx/spdx-3-model/blob/develop/docs/format.md>
- SPDX examples: <https://github.com/spdx/spdx-examples>
- SBOM example using SPDX 3.0 AI and Dataset profiles: <https://github.com/bact/sentimentdemo>
- NTIA Conformance Checker test corpus: <https://github.com/spdx/ntia-conformance-checker/tree/main/tests>
- Validator: `spdx3-validate` on PyPI
  (<https://pypi.org/project/spdx3-validate/>);
  GitHub: <https://github.com/JPEWdev/spdx3-validate>

## Other resources

- Reproducible Builds -- `SOURCE_DATE_EPOCH` specification (the timestamp
  convention Pitloom honours for deterministic SBOM `created`/`builtTime`
  fields and embedded-wheel ZIP entries):
  <https://reproducible-builds.org/specs/source-date-epoch/>
- Agent Skills standard <https://agentskills.io/>
- SARIF (standard format for static analysis)
  - <https://sarifweb.azurewebsites.net/>
  - <https://docs.oasis-open.org/sarif/sarif/v2.1.0/csprd01/sarif-v2.1.0-csprd01.html>
  - <https://github.com/microsoft/sarif-tutorials/>
