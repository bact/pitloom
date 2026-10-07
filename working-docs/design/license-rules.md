---
Created: 2026-10-05
Last-Modified: 2026-10-07
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Licence rules: taxonomy, cascade and conflict resolution

See also: [license-layers.md](license-layers.md) (content, source and
shape: what moves upstream),
[license-typing.md](../implementation/license-typing.md) (what PR #276
built), [license-pipeline.md](../implementation/license-pipeline.md)
(readers and call sites),
[license-pr276-followups.md](license-pr276-followups.md) (groups A/B/C),
[fragment-merge-unification.md](../implementation/fragment-merge-unification.md)
(licences in a merge),
[multi-source-conflict.md][msc] and
[generic-multi-candidate-fields.md](generic-multi-candidate-fields.md)
(conflict model).

Status: input for a later redesign of licence conflict resolution and
cascading. Sections 1 to 8 record the behaviour shipped in PR #276
(element typing), #283 (sdist licence detection) and #284 (fragment
merge), checked against `src/pitloom` on 2026-10-05.
[Open questions](#open-questions) records what is not settled, with the
evidence and the user's leanings. A leaning is input, not a decision.

## Goal

Explicit rules for licence sources, normalisation and conflict
resolution, applied identically on every surface. Each recorded value
shall be:

- **deterministic**: same input, same bytes, on every surface;
- **correct**: what the source said, as the SPDX term that means it;
- **not overclaimed**: no licence, conclusion, conflict or agreement that
  Pitloom does not have;
- **provenance recorded**: whose statement, which field, how changed.

## 1. Source taxonomy

Sources by kind, with the `Source:` label that decides the statement
class (section 4):

- **Manifest fields.** `project.license` (PEP 639 string, or a `text`/
  `file` table), `setup.cfg` `metadata.license` (inline or `file:`),
  `setup(license=...)`, Hatchling core `license_expression`/`license`,
  Poetry `license`; Core Metadata `License-Expression` and `License` in
  a wheel `METADATA` or sdist `PKG-INFO`. Labels: `pyproject.toml`,
  `setup.cfg`, `setup.py`, `Hatchling build backend`, `wheel METADATA`,
  `sdist PKG-INFO` (matched without case).
- **Classifiers.** `License ::` trove classifiers from the same carrier
  (`project.classifiers`, `metadata.classifiers`,
  `setup(classifiers=...)`, Hatchling `core.classifiers`, Core Metadata
  `Classifier`). Provenance names the field (`Field: Classifier` on a
  Core Metadata label). Not read for Poetry: `poetry-core` derives the
  classifier from `license`.
- **In-package files.** `license:` in `CITATION.cff`, then
  `codemeta.json`, then the text of `LICENSE`/`LICENCE`/`COPYING`/
  `COPYRIGHT` (with `""`/`.txt`/`.rst`/`.md`) identified by `licenseid`
  (threshold 0.85, file cap 256 KiB). One rule:
  `apply_in_package_license()` over `license_from_candidates()`. Read on
  a directory, by the hook and in an sdist; not in a wheel or installed
  metadata.
- **Installed metadata.** Core Metadata of an installed distribution.
  Three uses: the project's own in-tree `.egg-info`/`.dist-info`
  (reconciled into a directory read; label: the directory name); a
  dependency's installed copy in a project SBOM (`installed metadata`);
  a `loom env` package's own copy (`deployed package metadata`). A
  dependency's copy is used only when its version equals the expected
  one (PEP 440).
- **PyPI JSON API.** Dependencies and `loom env` packages, not
  offline: `license_expression`, `license` (skipped over a length cap),
  then `classifiers`. Label `PyPI JSON API`.
- **AI model file.** The format's own metadata (today PT2
  `extra/license`); others carry none.
- **Model card, local.** `license:` in a local README/model card front
  matter, by `ReadmeEnricher`, only with `[tool.pitloom] enrich` on.
- **Hugging Face Hub.** Card YAML `license:`, then the repository's
  licence files through `licenseid`. Label `Hugging Face Hub`.
- **Per-file tag.** A source file's `SPDX-License-Identifier:` (first
  one only). Not a cascade: a stated value is emitted at once.
- **Library caller.** `ProjectMetadata(license_name=...,
  license_concluded=...)`, with or without provenance.

Not sources today: GitHub, agent/skill fragments other than through a
fragment merge (section 5), dataset licences (`DatasetMetadata.license`
is not emitted), lock files (carry none).

## 2. Value classes: absent, weak, final

`classify_license(raw)` (`extract/_license_classify.py`) is the one
classifier; `get_or_create_license_element()`
(`assemble/spdx3/_license_elements.py`) the one builder.

- **Absent**: `None`, empty, whitespace only. No element, no
  relationship, declared or concluded, on any surface. SPDX 3: a missing
  `hasDeclaredLicense` is not `NoAssertionLicense`. Pitloom's own
  `NOASSERTION` fallback was removed in #276.
- **Weak**: `NOASSERTION` or `UNKNOWN`, any case. Recorded as the
  `expandedlicensing_NoAssertionLicense` individual, only when a source
  literally said so, and only when no later source in the same cascade
  states a licence. A raw spelling other than `NOASSERTION` (e.g.
  `UNKNOWN`) goes to `Normalized-From` on the relationship.
- **Final `NONE`**, any case: the `NoneLicense` individual. A statement:
  it ends a cascade (PyPI is not asked) and conflicts with a real
  licence.
- **No licence by structure**: the bare `License :: OSI Approved`
  (`_CATEGORY_CLASSIFIER`, the only category among the trove's licence
  classifiers) is dropped silently, alone or beside a child; a trove
  parent of another classifier in the set is dropped. The cascade goes
  on as if absent.
- **Real**: `expression` (strict parse, every id listed, canonical form;
  or a grammar-gap expression such as `Apache-2.0+`,
  `WITH AdditionRef-x`) or `text` (anything else; a newline or over 200
  characters is text without parsing).
- **Vague (Hugging Face only)**: card `other`, `custom`, `proprietary`,
  `unlicensed` give nothing and trigger file detection; `unknown` also
  triggers detection, and if detection finds nothing it is returned as
  stated, so becomes `NoAssertionLicense`. `NOASSERTION` on a card is not
  in the vague set: no detection.

A blank declared value (`License:` present but blank) is absent for the
cascade and gives no relationship; reconcile still treats it as "declared,
no value" (its provenance is present).

## 3. Cascade order per surface

One weak-cascade rule, `first_license()` (`extract/_core_metadata.py`):
the first candidate that states a licence wins, except that a weak one
gives way to any later real one; the first weak one is kept when nothing
real follows. `license_cascade(fields, classifiers)` applies it to a
field list followed by the classifiers;
`core_metadata_license_with_source()` is the Core Metadata instance
(`License-Expression`, `License`, `Classifier`, each unfolded).

- **Directory, `pyproject.toml`** (`loom project`, library, sdist without
  `PKG-INFO`): `project.license` (a `text`/`file` table that `licenseid`
  identifies gives the id) -> `project.classifiers` -> in-package files.
  Poetry: `license` -> in-package files.
- **Directory, `setup.cfg`/`setup.py`**: `setup(license=)` -> `setup.cfg`
  `license` -> `License ::` classifiers (`setup.py`'s, else `setup.cfg`'s),
  by `license_cascade()`: a field beats a classifier in either file, and a
  placeholder gives way to a real value in the other file; then in-package
  files. Real vs real: `setup.py`'s is kept, the other recorded as a conflict
  (`_setuptools_options.py`; setuptools-support.md#precedence).
- **Directory reconcile** (`loom project`, library; not the hook, sdist,
  wheel or `embed-wheel`): the result above against the in-tree installed
  metadata (`_installed_reconcile.py`). Static wins a real disagreement
  (`field_conflicts`, one `WARNING:`); installed fills an undeclared
  field; a weak static value gives way to a real installed one, with its
  provenance.
- **Hatchling hook**: `core.license_expression or core.license` ->
  `core.classifiers` -> in-package files.
- **sdist**: `PKG-INFO` by the Core Metadata cascade, else the
  `pyproject.toml` rule; then in-package files among the root members of
  `PKG-INFO`'s top directory (#283).
- **Wheel** (`loom wheel`, `wheel --embed`): Core Metadata cascade only.
- **`embed-wheel --project-dir`**: the wheel's Core Metadata cascade;
  the directory's detection only as the G2 concluded value, and only
  when the wheel declares a licence (`_add_concluded_license`); none
  for an sdist `--project-dir`.
- **`loom env` package**: the dependency cascade below, with the
  `deployed package metadata` label for its installed copy (declared).
- **Dependency in a project SBOM**: installed copy (Core Metadata
  cascade) -> PyPI record (its own cascade) -> the held weak value
  (`WeakLicense`, `emit_weak_license`). The held state is per dependency.
- **AI model in a project or `loom model`**: the model file's licence;
  with enrichment on, a local model card fills it only when empty.
- **Hugging Face model**: card value (canonicalised by `licenseid` id
  lookup) unless vague -> repository licence files -> card `unknown`.
- **Per-file tag**: no cascade.

The order lives in each reader's own field list; there is no declared
order table and no test that checks the readers against one.

## 4. Declared or concluded

A single value: `is_license_concluded()`
(`assemble/spdx3/_provenance_encoders.py`) by the `Source:` label alone.
Concluded when the source is in `THIRD_PARTY_SOURCES` (`pypi json api`,
`installed metadata`) or there is no source; declared otherwise. A
`Method` (e.g. `licenseid_detection`) does not change whose statement it
is. So in-package files, model cards, the Hugging Face repository, an AI
model file and the package's own installed copy are declared.

`TRANSPARENT_SOURCES` in the same module is a different set: it decides
only whether provenance is high-signal (written at `detail = "minimal"`),
not the statement class.

Two candidates (G2, main package only): when the manifest states a
non-blank value, it is declared and the in-package detection is the
concluded second opinion (`metadata.license_concluded`). A weak manifest
value counts as stated here (`apply_in_package_license` tests for a
non-blank string, `first_license` would treat it as weak).

Library: `ProjectMetadata(license_concluded=...)` with no
`license_name` is always `hasConcludedLicense` (the caller named the
slot).

Text to id (`detect_license_from_text`, `extract/_license.py`, #286), on
top of `licenseid` (0.4.2 or later; also checked on 0.3.7) at threshold 0.85:

- Read twice: as written, and with copyright notice lines removed (SPDX
  matching guidelines omit the notice); only the reading whose top score
  is higher counts, both when their top scores are equal, as when both
  reach the 1.0 cap (#287). A notice hides MIT from `licenseid` (PyYAML
  gives `Xnet`) but anchors licence placement in mixed content
  (ast_serialize).
- A stated licence (the manifest's value; any id an expression names)
  wins when it scores within 0.01 of the top in that reading:
  `licenseid` ranks near-variants above the verbatim text (`Pixar` over
  `Apache-2.0`, `JSON` over `MIT`). Against a top match at the 1.0 cap
  the score no longer tells how close they are, so the stated licence
  must also not fit measurably worse (`_fits_worse`, #287): `JSON`,
  `Xnet` or `FSL-1.1-MIT` stated over a verbatim MIT text concludes `MIT`
  and the mismatch stays visible; below the cap the score still orders
  (requests: stated `Apache-2.0` 0.9921 over `Pixar` 0.9963, though
  Pixar fits better). Until #287 either reading could hold the stated
  licence: a near-variant on top of the weaker reading, with the notice
  (iniconfig, pytest: `FSL-1.1-MIT`; attrs: `MIT-advertising`), won over
  the verbatim MIT text of the other.
- With nothing stated, the better-scoring reading decides (of readings
  tied at the top, the first that decides, so the as
  written one when both decide: #287): its top match, unless another
  licence family scores within 0.01 (a runner-up below the 0.85
  threshold counts), then none. A worse reading never overrides a
  tie (PyYAML's notice before a JSON/MIT tie would give `Xnet`).
  `X-only` and `X-or-later` are one family: a verbatim GPL text scores
  both alike (pylint: 1.069 vs 1.060 in 0.3.7, both 1.0 in 0.4), so
  the top match stays, as before #286.
- A runner-up that fits the input measurably worse is no tie (#287): its
  `similarity`, or the share of its licence the text holds (`coverage` up
  to 1; above 1 the text only has extra words), more than 0.01 below the
  top's (`_fits_worse`). Needed since `licenseid` 0.4 caps `score` to 1:
  MIT's 1.0157 against `JSON` 0.9926 became 1.0 against 0.9926, and
  `FSL-1.1-MIT` (similarity 1.0, coverage 0.25: MIT's text is a quarter
  of it) ties MIT at 1.0. The list order is `licenseid`'s ranking, kept
  for equal scores. Same result on the corpus with 0.3.7 and 0.4; an
  unmeasured field (a mock, a non-text match) never breaks a tie.
- Consequence: the concluded value now leans on the declared one in a
  near-tie, e.g. `-only` vs `-or-later` (astroid, pylint): the second
  opinion agrees with the manifest where the text cannot tell.
- Measured on 90 installed licence files: 66 right, 10 wrong, 14 none
  before; 76/4/10 stated, 73/4/13 unstated. The 4 wrong are composite
  files (mypy, typing_extensions, mkdocs-material, poetry-core); counted
  before the family and both-readings refinements. Reading twice doubles
  the matcher time (MIT 0.25 s to 0.56 s). Corpus:
  `tests/fixtures/license-texts/`. Upstream issues (not filed): notice
  hides MIT; near-variant outranks verbatim text.

## 5. Conflict model

- **G2 declared vs concluded** (`build_license_elements`): both
  relationships always built; a `provenance/conflict/1` Annotation
  (`field: license`, roles `declared` and `detected`) when the two
  values differ by `same_licence`. `NoAssertionLicense` on either side
  never conflicts; `NONE` against a real licence does.
- **Reconcile** (static vs in-tree installed): the same `same_licence`
  after classification; weak agrees with anything; a disagreement goes
  to `field_conflicts` with both candidates `role: declared`, static
  kept.
- **Cascade**: the first stating source wins and later sources are not
  read or compared. No conflict is recorded between, e.g., a manifest
  field and a classifier, installed and PyPI, a model file and its card,
  or a Hugging Face card and the repository `LICENSE`.
- **Fragment merge** (#284): licence elements unify by `license_key()`
  (base first, then configuration or file-name order, then id order
  within a fragment), with a unification Annotation per dropped element.
  The merge compares elements, not a package's licence relationships: a
  fragment's second `hasDeclaredLicense` for the same package is kept
  beside the first, with no conflict Annotation (code reading).

Today's model is two candidates at most, for the main package only.

## 6. Equivalence

- **Expressions**: canonical form from the strict parse (listed id case,
  upper-case operators, sorted terms of a flat one-operator list,
  repeats collapsed, deprecated `X+` replaced by `X-or-later`); a
  grammar-gap expression canonicalised around placeholders. A bare
  deprecated `GPL-2.0` stays as written. A nested mixed AND/OR may keep
  more than one spelling (the library's absorption is not confluent).
- **Several classifiers**: one `LicenseExpression`, the AND of
  `LicenseRef-pitloom-classifier-<name>` terms sorted by classifier, with
  `customIdToUri` to each name's text element; one `WARNING:` per set.
- **Text**: equal when equal after `str.strip()`. The element stores the
  first-seen text less leading blank lines/spaces/tabs and final line
  breaks (`_without_blank_ends`). Inner text, CRLF included, is kept and
  compared as written.
- **Name vs id**: `same_licence(a, b)` is equality, or one is the SPDX
  List name of the other's listed id, any case (`is_listed_name`, a
  stop-gap until `licenseid` maps names). Not applied to an AND of
  classifier terms.
- **Kind**: an expression and a text of the same string are two
  elements (`(kind, value)` key).

## 7. Provenance per value

Keys: `Source`, `Field`, `File`, `Package`, `Method`, `Tool`,
`Normalized-From`, `Normalizer` (only when a parse took place),
`Deprecated-License-Id`.

- On the element when this source created it; on the source's own
  relationship when the element already existed and the value carries a
  note (`LicenseElement.noted`); always on the relationship for an
  individual (it cannot carry an Annotation).
- Written at `detail = "minimal"` only when high-signal (a `Method`, a
  normalisation note, or a non-transparent source); always at
  `"full"`.
- A weak value a later source replaced leaves no record.
- A reused element keeps the first creator's provenance.

## 8. Determinism and tie-breaks

- Classifiers sorted and deduplicated before use (Hatchling sorts, a
  source may not).
- Canonical term order in expressions.
- Text: blank ends dropped once, in the builder; readers do not strip.
- Text dedup keeps the first-seen spelling: deterministic only because
  build order is.
- Licence file pick: the list's own spelling, else the smallest name in
  `str` order, never listing order.
- One `WARNING:` per value per process (`warn_once`).
- Fragment merge: base, then configuration/file-name order, then id
  order.

## Rulings on record

From the PR #276 decision log (R1-R10, 2026-10-03/04), not written down
elsewhere:

- `UNKNOWN`/`NOASSERTION`/`NONE` and the warning operators match in any
  case (option A).
- A grammar-gap value is recorded as an expression (raw, operators
  upper-cased), with an upstream `py-spdx-license` issue to follow.
- An unknown id alone (`Apache2`) stays silent text in 0.20.0. The
  0.21.0 warning for a field that must hold an SPDX expression
  (`project.license`, `License-Expression`) needs the source field
  threaded through about six readers.
- Several classifiers: first "sorted first plus one `WARNING:`" (M2),
  superseded the same day by the AND form, chosen to match the G7 #3
  dataset list (`[a, b]` is `a AND b`).
- A lone `License :: OSI Approved` was first proposed as a name; the
  user ruled it "no licence" (R8).
- Text blank ends grew in three steps (one final break, all final
  breaks, then leading blank space, L1): every step was surface parity,
  since a Core Metadata reader loses what a file keeps.
- After R10, no further licence-content questions in #276; the findings
  below were recorded instead.
- An unstated verbatim GPL-family text concludes the `-only` id
  `licenseid` ranks first, as 0.19.0 did, not none (user, 2026-10-05, PR
  #286: the conservative choice; the text cannot tell `-or-later`).

## Open questions

Each item: the evidence (R10 unless noted) and, where given, the user's
leaning (2026-10-04).

1. **Weak manifest value vs a real licence elsewhere.**
   `license = "NOASSERTION"`/`"UNKNOWN"` with an MIT `LICENSE` gives
   declared NoAssertion, concluded MIT; a silent manifest gives declared
   MIT. Common: old setuptools wrote `License: UNKNOWN` into every sdist
   with no licence. A model file's `UNKNOWN` blocks the model card's
   licence (`ReadmeEnricher` fills only an empty value). Leaning: the
   real one is declared, the weak value noted in provenance "as the
   dependency cascade does" (but see 9: that cascade records nothing).
2. **Weak value across merged manifest files** -- ruled (#287).
   A placeholder (`UNKNOWN`/`NOASSERTION`) in one of `setup.py` and
   `setup.cfg` gives way to a real licence in the other, as in
   `first_license`. (setuptools itself keeps `setup.py`'s `UNKNOWN`: an
   accepted difference.) Open for `[project]` vs `[tool.poetry]`.
3. **Reconcile ranking.** Silent `setup.cfg`, MIT `LICENSE`, egg-info
   `License-Expression: Apache-2.0`: the detection is kept as declared
   and the project's own installed record becomes the conflict. Leaning:
   installed metadata outranks a `LICENSE` detection for declared; the
   detection stays the concluded second opinion; the conflict recorded.
4. **`setup.cfg` vs `setup.py` field order** -- ruled for setuptools
   (#287): `setup.py` over `setup.cfg`, as setuptools does; a real
   disagreement keeps `setup.py`'s as the one declared licence and records
   the other as a conflict. Still open: the same question for other merged
   sources (pyproject with Poetry), no leaning on a general rule.
5. **Cascade choices not recorded.** A model file's `Apache-2.0` and its
   card's `mit`: the card is skipped, nothing records the disagreement.
   Same for any two cascade sources. Open: which choices may never be
   silent; N candidates instead of two
   ([generic-multi-candidate-fields.md](generic-multi-candidate-fields.md)).
6. **One order table per surface**, tested against every reader. Gaps:
   no detection for a wheel (needs `License-File:` selection, 0.21.0)
   or installed metadata; `embed-wheel --project-dir` records nothing
   for a silent manifest plus a `LICENSE` where `loom project` and the
   hook declare it; `license = file: LICENSE` in `setup.cfg` is recorded
   as the text `file: LICENSE` (setuptools rejects it).
7. **Several-classifiers `WARNING:` for a discarded value.** An in-tree
   egg-info with two licence classifiers warns "recorded as ... AND ..."
   while reconcile keeps pyproject's `MIT`.
8. **Hugging Face vague values.** A card `unknown` reads the repository
   `LICENSE`; `NOASSERTION`/`noassertion` does not. Also: a non-vague
   card value means the repository files are not read at all, so there
   is no second opinion; `other`/`custom` with nothing detected give no
   value, not a weak one. No leaning.
9. **Provenance.** A reused element keeps the first package's provenance;
   later reusers record none unless their value was normalised, so
   `loom env` shows zipp's MIT tagged with another package. A replaced
   weak value is not recorded. A library caller's licence with no
   provenance gets a default label
   (`attach_main_package_license`: `Source: pyproject.toml | Field:
   project.license` for `license_name`, `Source: LICENSE | Method:
   licenseid_detection` for a lone `license_concluded`, and in G2 the
   declared label for a concluded value with none): overclaimed. Open:
   the keys every value must carry; the `method` vocabulary
   ([provenance-enrichment-vocabulary.md](provenance-enrichment-vocabulary.md)).
10. **Text equivalence.** CRLF and LF texts are two elements. Leaning:
    normalise inner CRLF/CR to LF (line endings are encoding, not
    content), everything else inner kept as written. A licence `name`
    keeps a trailing `\r` or spaces of the text's first line. A
    classifier with a trailing space is read as a name on every surface
    but `setup.cfg` (which strips), so `"License :: OSI Approved "` is
    recorded as the licence `OSI Approved`; one with a leading space is
    not read as a licence classifier at all. Open too: text case and
    inner spacing; `LicenseRef-` case; nested AND/OR spellings.
11. **Classifier or licence name to id** (layer 1, upstream `licenseid`):
    names and listed full texts stay `SimpleLicensingText`, a known
    deviation; name-only case differences give two `LicenseRef-` terms.
12. **Detected text by surface.** A `license.file` text `licenseid`
    identifies is the id on a directory and the hook, the text from an
    sdist, wheel or installed metadata (`stated_license()` is not run on
    `PKG-INFO`). A content decision
    ([metadata-quality.md](metadata-quality.md)).
13. **Roles to SPDX relationships.** `role` maps to a relationship only
    in G2; a single value maps by source class. Open: one mapping table;
    a role on a single value; SPDX 3.1's exactly one concluded licence
    (Pitloom emits none when no source concludes one).
14. **Source classes.** Open: a typed class carried with the value
    instead of a label lookup; where the Hugging Face Hub, GitHub and
    agent sources sit; the same weak/final classes for non-licence
    fields.
15. **Fragment merge.** Shipped in #284 (the leaning was "own PR before
    0.20.0"). Left: `customIdToUri` targets in other namespaces are not
    checked; expandedLicensing elements are not unified; a user's
    `LicenseRef-` unifies by string, not by its map; licence
    relationships of one package across fragments are not compared
    (section 5). See
    [open-items.md][open-items].
16. **Tie-breaks as rules.** Each tie-break in section 8 is code, not a
    written rule; first-seen text spelling depends on build order.

[msc]: ../implementation/provenance/multi-source-conflict.md
[open-items]: sbom-fragments/open-items.md#left-after-the-fragment-merge-fixes
