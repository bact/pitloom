---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pre-release review 0.25.0: the docs and skills batch, and the sweep

See also: [../pre-release-review-0.25.0.md](../pre-release-review-0.25.0.md)
(gates, triage, fix plan, the code batches #559-#561),
[findings-docs.md](findings-docs.md), [findings-code.md](findings-code.md).

Branch `release-docs-sweep`, on main after #561. PR C of the fix plan,
merged with the standing sweep ("no stale, no unused"). Every claim written
was checked by running it (offline) or reading the code.

## Review items

- **TRY-1, TRY-6** (ruled: caveat): `docs/fragments.md` says the merged
  check can fail two valid SBOMs whose `created` differ (spdx3-validate joins
  the files' blank nodes by label, `_:CreationInfo0`), suggests `--no-merge`
  for separate SBOMs and `loom merge` output for a base with its fragments,
  that an enrichment fragment fails on its own and paired with its base, and
  that no `FILE=... STATUS=valid` line is printed unless every check passed
  (also `docs/cli.md`, Output). `skills/sbom-validate/SKILL.md` and its
  examples say the same. Reproduced: two `loom project` SBOMs a minute apart
  fail merged, pass `--no-merge`.
- **TRY-2**: the evaluation example uses `add_validation_dataset()`; the
  bullets say `add_dataset()` is `trainedOn` in a `set_model()` run and
  `testedOn` in a `use_model()` run; a blank name is `option-invalid`
  (checked for every loom call taking a name). `sbom-enrich`'s
  `minimum-elements-g7.md` too.
- **CLI-7** (#561): `docs/ai-model-formats-hugging-face.md` (the two
  `input-not-found/hub` lines, private models, page URLs of a one-part id
  with the page kinds `_PAGE_SEGMENTS` holds, a login-only page refused as a
  two-part id, a dangling link is a local path), `docs/cli.md`,
  `docs/python-api-remote.md` (`huggingface.repository-not-found`), the
  `sbom-generate` examples and known limitations.
- **Library argument checks** (#557, #559-#561), each run: `docs/api.md`
  (empty `project_dir=`; the URL argument of the Git and PyPI functions and
  `fetch_git_project()` is now checked: `TypeError`/`ValueError`,
  `option-invalid`), DOC-1 in `docs/python-api.md`, the new tracking page and
  `docs/python-api-remote.md` (a wrong type is `TypeError`, an integer below
  1 `ValueError`; `sbom_kind=`/`kind=` choices; an empty PyPI URL is
  `option-invalid`), REG-1 (a missing `loom.run` registry is
  `FileNotFoundError`, `input-not-found`), the `IdRegistry` refusals of #560
  in `docs/id-registry.md`, `docs/wheel-sbom.md` (`embed_wheel_sbom()`), the
  blank `--creator-name/--creator-email/--creation-tool` refusal in
  `docs/cli-flags.md`, and a Git URL with no host (`git-url-invalid`, "the
  URL names no host") in `docs/git-urls.md` and `docs/python-api-remote.md`.
- **MSG-1**: `docs/ai-model-scan-limits.md`, `docs/python-api.md` and the
  by-surface table of `docs/url-credentials.md` give the `ConfigOverrides`
  form for `embed_wheel_sbom()`. **MSG-3**: the PyPI comment names the
  library line. **HOOK-4**: the page quote carries `Pitloom build hook:` and
  says the build fails.
- **DOC-2** (an unknown provenance `schema` is `config-invalid` at read,
  run), **DOC-3** (the `loom:` frame also covers an argument the command does
  not take; wording fixed, the frame itself is next release), **DOC-4**
  (`docs/url-credentials.md` header), **DOC-7** (See-also near the top of
  `configuration.md` and `python-api.md`).
- **DOC-5**: `docs/python-api.md` (31,858 bytes) split: the tracking
  decorator moved to `docs/python-api-tracking.md` (16.9 KB); the old
  heading stays as a stub so `python-api.md#tracking-decorator` resolves;
  the six inbound links point at the new page; `mkdocs.yml` nav.
  `docs/ai-model-formats.md` (16 KB) and `docs/git-urls.md` (18.6 KB) are
  under the cap: not split.
- **TRY-9a**: `docs/cli.md` and `docs/id-registry-create.md` give the
  catalogue's remedy (delete, then `loom id import` the last SBOM to keep
  the ids). The line itself still has no action: next release (output).
- **TRY-11**: `labels` defined; the history clause dropped; the source path
  in `docs/id-registry.md` is now the Python name; `id generate ... -e
  models/classifier.onnx` (pins the file, run) instead of `--entity model`
  (`registry-path-key-unusable`); the skill example uses `my-pkg@1.0`.
- **CLI-6**: `docs/cli.md` says only `describe-relationship` and
  `update-id-registry` are noted; `pretty` (and `use-lockfile` in the hook)
  are not yet.
- **ACT-3**: the YAML comment says a `pitloom-version` must be 0.25.0 too.
  **ACT-4**: the `action.yml` comment names argparse's untagged usage block.
  **ACT-5**: `Last-Modified`. **MSG-4**: the `refuse_hub_model_target`
  docstring names both surfaces' wording.
- **REG-2, SKL-3, SKL-4, SKL-5, SKL-6**: done in the skills (SKL-5 keys on
  `[option-no-effect]`, which the `Build:` form ends in too).
- The #412 `%2F` line (`docs/git-urls.md`): current; both refusals reproduce
  offline. Nothing to change.

## The sweep

- **Docs**: a fresh read of every non-generated page against the code and
  `--help`; three more pages fixed (`cli-flags.md`: `-v`'s `PROJECT_DIR`,
  `--update-id-registry`, the `--scan-model-usage` hint, the creator flag
  refusals; `metadata-provenance.md`: a wrong conflict example;
  `wheel-sbom.md`: empty paths).
- **Skills**: every `SKILL.md` and non-generated reference read in full
  against the code; `add_parser(` subcommands against the descriptions (no
  new gap; `loom merge` and `fragment list` stay the known one). Budgets:
  `sbom-enrich` body 16,371, `sbom-generate` 16,275, `sbom-validate` 13,159
  of 16,384 bytes; descriptions 1,005, 1,021, 999 of 1,024 characters.
- **Working-docs**: 28 design files describing merged work moved to
  `implementation/` (the catalogue PR plans and builds, the sweep C plans,
  `credential-detect-and-refuse.md`, `message-frames-forward.md`), links
  rewritten; two files over 30 KB split
  (`design/provenance-taxonomy/findings-to-fix-first.md`,
  `implementation/message-catalogue-sweep-c2-plan.md`); `roadmap.md` ticked
  and condensed; stale 0.24.0 targets and "PR pending" lines updated; three
  dead links fixed. Removed: the empty headings 6-10 of
  `message-catalogue-pr16-build.md`.
- **Code** (no behaviour change): stale docstrings (`_config.py` named a
  constant that never existed, `hatchling.py` the CLI's reader, a test the
  removed `_build_document_model()`); every dotted Sphinx role resolves.
  Removed as unused (the definition the only hit of `git grep -nw`): the
  `fixtures_dir` fixture (`tests/conftest.py`), `_GEN`/`_DERIVED`
  (`test_fragments_generated.py`), `_CONTROL_IDS`
  (`test_url_masking_boundary.py`), `Reader` and its `Callable` import
  (`test_provenance_hostile_labels.py`), `_SBOM_ARC`
  (`test_extract_wheel_sbom.py`). `tests/messages/test_drift_quotes.py`
  gains the marker `the URL names no host`, so a quote of that line is
  checked.

## Left

For the bump PR: SKL-1, SKL-2, HOOK-6, `docs/agent-skills.md:53-56`, the
LicenseID version text in `docs/metadata-provenance.md:60` and
`metadata-provenance-licences.md:58,116`, the citation in `docs/index.md`.

Next release:

- `credentials-unsafe/git-userinfo`'s summary names "an empty host", which
  the CLI now refuses earlier as `git-url-invalid`; `_git_credentials.py:192`
  keeps the branch. Check whether any route still reaches it, then drop the
  clause or the branch.
- `docs/g7-sbom-for-ai.md:87,248` cite coverage figures "as of 0.23.0":
  re-run `scripts/g7_coverage_report.py` with the `conformance` group.
- `skills/sbom-generate/references/known-limitations.md` is 29.3 KB.
- About 35 `message-catalogue-*` files sit flat in `implementation/` (the
  3+-files subfolder rule); grouping the three credential docs needs the
  path in `tests/core/url_masking/test_url_masking_nested_values.py:9`
  changed with it.
- TRY-9a's catalogue line (`registry-wrong-format`) has no action.
- A `str` given as `pitloom_config=` to `generate()` or
  `generate_wheel_sbom()` raises an uncoded `TypeError` (`replace() should be
  called on dataclass instances`); `IdRegistry.new(1)` and `IdRegistry(1)`
  (a namespace that is no string) raise uncoded `TypeError`s. Found by the
  review of this batch; LIB-9's family.
- `read_wheel("")` raises `target-wrong-format` naming `FILE=.` (`not a
  .whl file`), where every generate and embed function says
  `input-not-found` for an empty wheel path. Found by the review of this
  batch.
