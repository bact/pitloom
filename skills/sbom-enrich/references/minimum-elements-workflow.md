---
Created: 2026-09-29
Last-Modified: 2026-10-21
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Complete a standard's minimum elements: step detail

See also: `../SKILL.md` ("Complete a standard's minimum elements", steps
a-g, which hold the rules) and `minimum-elements.md` (the checklists,
field mappings; `minimum-elements-datasets.md` has the G7 Dataset Properties
cluster, `minimum-elements-questions.md` the question bank).

## Step d: ranking the questions

Lead with effort-to-impact, not checklist order. Before asking, rank the
remaining gaps: quick answers (a plain yes/no, a fact the user obviously
already knows) and answers that resolve multiple elements or multiple
standards at once go first (e.g. setting `[[tool.pitloom.creator]]` closes
both `SBOM Author` and the main package's `suppliedBy` in one
step -- see `minimum-elements.md`'s NTIA "Supplier Name" row for why). Say
up front which few answers would close most of the remaining gap, so the
user can judge where their time actually pays off -- don't just work a
flat list top to bottom.

The user can stop with "stop", "that's enough", "skip the rest" or
equivalent. That is not a failure, and there is no need to insist on an
answer first.

## Step g: why `NOASSERTION`

An element the user leaves unknown is written as `NOASSERTION`/"unknown"
in the fragment, following CISA 2026's "Explicitly Identifying Unknown
Information" practice: a stated unknown is a decision, a missing field
is indistinguishable from an oversight.

For a licence the user says is unknown, write a `Relationship` with
`relationshipType` `hasDeclaredLicense` (or `hasConcludedLicense`), `from`
the package's id and `"to": ["expandedlicensing_NoAssertionLicense"]`. No
licence element is created, and never a `SimpleLicensingText` reading
"NOASSERTION". Pitloom itself writes no licence relationship for a licence
nobody stated.

## Cross-check with the checker

Optional, never a replacement for the mandatory `sbom-validate` pass (shape
and SHACL validity), and not run unless the user asks for it or agrees: it
installs a package that is not on PyPI (non-interactive: install nothing;
run it only if `sbomcheck` is already on `PATH`, else list the commands
below in the report). The community `ntia-conformance-checker`
(`sbomcheck`) checks SPDX 3 against all five standards. Install the build
Pitloom pins, with the `pip install` line on Pitloom's "G7 SBOM for AI"
page, "Check an SBOM"
(<https://bact.github.io/pitloom/g7-sbom-for-ai/#check-an-sbom>; it names
the commit). Then, per standard:

```bash
sbomcheck -s spdx3 -c ntia     -r json -o ntia.json     sbom.spdx3.json  # NTIA 2021
sbomcheck -s spdx3 -c fsct3    -r json -o fsct3.json    sbom.spdx3.json  # FSCT 2024
sbomcheck -s spdx3 -c cisa2026 -r json -o cisa2026.json sbom.spdx3.json  # CISA 2026
sbomcheck -s spdx3 -c g7ai     -r json -o g7ai.json     sbom.spdx3.json  # G7 SBOM for AI 2026
sbomcheck -s spdx3 -c bsi      -r json -o bsi.json      sbom.spdx3.json  # BSI TR-03183-2 v2.1
```

[Lumina](https://github.com/bact/lumina), a web UI, shows the same results from
an SBOM file or a SARIF log (`-r sarif`).

`-s spdx3` is required (the default is SPDX 2). `fsct3-min` still works for
`fsct3`, with a `WARNING:` that it is deprecated. `-r` also takes `sarif`
(each result has the `ruleId`, a message and the package's logical location; the
run's `properties.ruleOutcomes` maps every rule id to its outcome),
`sarif-sbom` (the same with the SBOM embedded), `html`, `none` and `print` (the
default). `print` and `html` are requirement-level tables with no rule ids and
no `out-of-scope` rules; `json` and `sarif` carry the ids. Without `-o` the
report goes to stdout. Exit status 0 means conformant, 1 not (also with `-r
none`); read the report either way. List the rules that need work:

```bash
python3 -c "import json,sys; [print(r['id'], r['provision'], *[f['name'] for f in r['findings']]) for r in json.load(open(sys.argv[1]))['ruleResults'] if r['outcome'] == 'missing']" bsi.json
```

Each line is a rule id, its provision and the names of the packages that miss
it (`BOM-BSI2025-COMP-004 requirement main`, from a `loom model` SBOM of an
ONNX file named `main`); a document-level rule names no package. No output
means nothing is missing.

Outcomes: `present` (the property exists; its value is not judged; a rule with
sub-rules, like G7's `MDL-006`, is `present` when any sub-rule is),
`missing`, `not-applicable` (nothing of that kind, e.g. no dataset, or a
BSI "if it exists" element the package does not give) and `out-of-scope` (the
checker does not check it: report it from `minimum-elements.md` instead, never
as passed). A `permission` rule (BSI COMP-015 and -017; COMP-016 is not checked) is optional.

Per `missing` rule, look the element up in `minimum-elements.md` and do the
first that fits:

1. **Pitloom can fill it from the project**: say which setting or input
   (`[[tool.pitloom.creator]]`, an e-mail in `[project].authors`, a `LICENSE`
   copyright line, a run without `--offline` for PyPI data, with the user's
   consent) and regenerate.
2. **A fragment can carry it** (project-directory base only): draft it from a
   local source or the user's answer (steps 6-10, step d's question bank),
   e.g. a `hasConcludedLicense`, a `dependsOn` with `completeness`, a
   distribution `software_File` with its SHA-512. Then re-run the checker.
3. **Otherwise report it as an open gap**, saying why: the user declined or
   could not answer; the base cannot merge a fragment (`loom model`, a wheel);
   no source exists (a dependency's SHA-512); SPDX 3.0.1 cannot record it
   (`out-of-scope` rules). Never write a placeholder to turn a rule `present`.
