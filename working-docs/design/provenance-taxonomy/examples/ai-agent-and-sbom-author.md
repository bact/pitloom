---
Created: 2026-11-16
Last-Modified: 2026-11-23
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Examples: asserters `ai-agent` and `sbom-author`

See also: [README.md](README.md) (sources of the inputs, how to read a
row, the matrix), [../asserter.md](../asserter.md),
[../basis.md](../basis.md).

No agent took part in the benchmark, so the `ai-agent` claims are
constructed on real inputs. For `sbom-author` the benchmark has a near
equal: its reviewer, a person who read the sources and supplied a value
where the tools gave none (the public file `data/reviews/arthit.jsonl`
of release 0.1, 85 decisions). A reviewer of a benchmark is not an SBOM
author, but stands where one stands.

## ai-agent, inferred

An agent worked the value out by judgement. The default.
Such a claim arrives in a fragment or an enrichment record that states
its asserter.

| # | Element | Input | Claim | Today |
| --- | --- | --- | --- | --- |
| AI-1 | `pkg:huggingface/coqui/XTTS-v2@6c2b0d7` | the card: `license: other`, `license_name: coqui-public-model-license`, `license_link: https://coqui.ai/cpml`; LicenseID finds no licence in the linked page | an agent reads the page and names the licence `LicenseRef-coqui-public-model-license` | yes, through the enrichment skill |
| AI-2 | a model card (constructed) | README prose: "fine-tuned on the SQuAD training set" | an agent names the dataset `squad` and the relationship `trainedOn` | yes, through the enrichment skill |

```text
AI-1  Source: https://coqui.ai/cpml | Kind: linked-document | Asserter: ai-agent | Tool: <agent> <version> | Basis: inferred
AI-2  Source: README.md | Kind: card | Asserter: ai-agent | Tool: <agent> <version> | Basis: inferred
```

Notes:

- **AI-1**: by the licence table an `ai-agent` licence claim yields no
  relationship; it is kept in the Annotation as a `passed-over` candidate.
  The card's own three fields stay `originator`, `declared`. The linked
  page had no source kind (the same gap as ST-1); since 2026-11-23
  it is `linked-document` ([../source.md](../source.md), rule 9).
- **AI-2**: the README is the originator's; the reading of its prose is
  the agent's.

## sbom-author, declared

The person or organisation making the SBOM said so, through a flag, a
configuration key, a library argument or a fragment. The default.

| # | Element | Input | Claim | Today |
| --- | --- | --- | --- | --- |
| SA-1 | `pkg:pypi/python-dateutil@2.9.0.post0` | its `LICENSE` holds an Apache 2.0 notice and the full BSD three-clause text; the match names the first (OL-2) | the SBOM author, having read the file, passes `license_concluded="Apache-2.0 AND BSD-3-Clause"` | yes |
| SA-2 | a file in a project (constructed) | `pyproject.toml`: a content type override under `[tool.pitloom]` | the content type of that file | yes |
| SA-4 | `pkg:cargo/ring@0.16.20` | no value from the tools; the reviewer's note: "Read from LICENSE-* files" | licence `Apache-2.0 AND ISC AND MIT` | yes, as `license_concluded` |
| SA-5 | `pkg:maven/com.buschmais.jqassistant.core/store@2.9.1` | no value from the tools; the reviewer's note says the source does not tell `-only` from `-or-later` | licence `GPL-3.0`, kept as written | yes, as `license_concluded` |

```text
SA-1  Source: <caller script> | Kind: caller | Location: license_concluded | Asserter: sbom-author | Basis: declared
SA-2  Source: pyproject.toml | Kind: config | Location: tool.pitloom.content-type.override | Asserter: sbom-author | Basis: declared
SA-4  Source: <caller script> | Kind: caller | Location: license_concluded | Asserter: sbom-author | Basis: declared | Note: read from LICENSE-* files
SA-5  Source: <caller script> | Kind: caller | Location: license_concluded | Asserter: sbom-author | Basis: declared | Note: cannot tell -only from -or-later
```

Notes:

- **SA-1** becomes `hasConcludedLicense` (licence table). The
  expression is an author's reading, constructed for the example; the
  file's last line says the BSD licence applies to all code, so another
  author may conclude otherwise. The file's own
  match stays a declared licence of the originator; the two stand in
  different slots and are no conflict.
- **SA-4** is the same file kind as the parked licence-file match
  ([originator.md](originator.md#a-licence-file-matched-to-an-id)), read
  by a person: three licences from several files, where a matcher names
  one id per file.
- **SA-5**: a statement with a stated doubt. The doubt is about the
  source's wording, not about how the author came to the value, so it
  is a `Note` and the basis stays `declared`. `GPL-3.0` is a retired
  id: the `Superseded` key applies.

## sbom-author, inferred

When the author says so.

| # | Element | Input | Claim | Today |
| --- | --- | --- | --- | --- |
| SA-3 | a model (constructed) | no source states the training data; the author knows the base model and writes a fragment | dataset, with `Basis: inferred` and a `Note` saying from what | no: a fragment has no key for it today |
| SA-6 | `pkg:maven/org.jboss.windup.exec/windup-exec@6.3.9.Final` | the reviewer gives `CC0-1.0` and notes that it "is not exactly" public domain, which is what the source appears to state (source not read here) | licence `CC0-1.0` | no key for it today |
| SA-7 | the model card of AI-2 (constructed) | the agent's claim AI-2; the SBOM author confirms it | dataset `squad` and the relationship `trainedOn`, now the author's | no: the skill has no act of confirming |

```text
SA-3  Source: <fragment file> | Kind: fragment | Asserter: sbom-author | Basis: inferred | Note: from the base model's card
SA-6  Source: <caller script> | Kind: caller | Location: license_concluded | Asserter: sbom-author | Basis: inferred | Note: CC0-1.0 is not exactly public domain
SA-7  Source: README.md | Kind: card | Asserter: sbom-author | Tool: <agent> <version> | Basis: inferred
```

SA-7 is AI-2 after the author confirmed it (ruled 2026-11-23;
[../asserter.md](../asserter.md), rule 8): the asserter changes, the
source and the agent stay.

**Q**: is this cell needed? An author who is unsure can leave the value
out. It is kept so that an author's guess is not read as a statement.
SA-6 is a real case for it: the author picked the nearest listed id for
a statement that has none, and said so. Against SA-5, where the doubt is
only noted: the line between the two is whether the value itself is the
author's approximation.

## Closed cell

`ai-agent` never has `declared`. The nearest input is an agent that copies
`license: mit` out of a card's front matter: the value is the originator's
statement, so the asserter stays `originator`
([../asserter.md](../asserter.md), rule 5), and the agent goes in `Tool`.
