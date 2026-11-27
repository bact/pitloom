---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pre-release review 0.25.0: findings in docs, skills, catalogue, Action, trial

See also: [../pre-release-review-0.25.0.md](../pre-release-review-0.25.0.md)
(gates, triage, fix plan), [findings-code.md](findings-code.md) (CLI,
library, hook, ID registry).

Each finding: id, severity as reported (`maj`/`min`/`nit`), bucket after
triage (**B** release blocker, **C** cheap fix for 0.25.0, **N** next
release), how it was confirmed (**R** re-run during triage, **K** read at the
cited line), the PR that introduced it where known ("pre" = before v0.24.0).
Paths are at `ff3960a1`. Commands ran as
`PYTHONPATH=<tree>/src .venv/bin/python -m pitloom` with
`SOURCE_DATE_EPOCH=1767225600` and `--offline`.

## Version text (one batch, at the version bump)

- **SKL-1** maj, **C** (PR D; the second opinion: prose, not an install
  command, pip resolves `>=0.9.3` anyway), R. Three skills say "LicenseID 0.8.4"
  (`skills/sbom-generate/SKILL.md:71`, `skills/sbom-enrich/SKILL.md:61`,
  `skills/sbom-validate/SKILL.md:85`); `pyproject.toml:68` requires
  `licenseid>=0.9.3,<0.10`, and `sbom-generate/SKILL.md:84` installs that.
  Repro: `grep -rn "LicenseID 0.8" skills/`. Not on the roadmap's cut sweep
  (`roadmap.md` "0.25.0 cut sweep" names only the Pitloom floor), and
  `tests/test_licenseid_floor_docs.py` matches only `licenseid>=` spellings.
  From 56f21fd2 (pre); #502 and #551 raised the floor without it. Re-check
  the behaviour clause ("reads `Apache Software License 2.0` ... does not
  warn about a missing licence database", `sbom-validate/SKILL.md:85-87`)
  against 0.9.3, length-neutral in `sbom-enrich`.
- **SKL-2** maj, **B** (tracked: roadmap "0.25.0 cut sweep"), R. `pitloom >=
  0.24.1` names no release; generated tables inside the skills already say
  `since 0.25.0`. 37 lines: `sbom-generate/SKILL.md:30,71-74,101,102,108`;
  `sbom-enrich/SKILL.md:27,61,64-67,217`;
  `sbom-validate/SKILL.md:26,85,88,90,99,103`;
  `sbom-generate/references/examples.md:31,33,66,68,70,89,149,155,218`;
  `sbom-enrich/references/examples.md:296,347`, `minimum-elements.md:208`,
  `pre-merge-check.md:35,36`; `docs/agent-skills.md:53,56` (same as DOC-6,
  TRY-4). Keep the "0.24.0 or later" PyPI-URL lines
  (`sbom-generate/SKILL.md:146,152`, `references/pypi-url.md:13,30-32`,
  `examples.md:61`). Budget: the `sbom-enrich` body is 16,372 of 16,384
  bytes, `sbom-generate`'s description 1,021 of 1,024 characters: only
  same-length swaps fit. From #482.
- **HOOK-6** nit, **C** (bump), K. `docs/hatchling-build-hook.md:28` says
  `pitloom>=0.23.4`, `README.md:135` `>=0.24.0`; the page quotes 0.25.0 lines.
- **ACT-3** nit, **C**, R by the reviewer against a v0.24.0 tree. The
  `url-credentials` inputs pass flags 0.24.0 lacks (exit 2 with an older
  `pitloom-version`); `docs/github-action.md:81-82,149-150` say only the tag
  needs 0.25.0.
- Bump cautions (from DOC-6, TRY-11, ACT-5): keep
  `docs/id-registry-keys.md:339` ("0.24.0 or earlier", history) and the
  deliberate `0.22.0` pins of `docs/id-registry.md:306-311,342,353` out of a
  blanket replace; `docs/github-action.md:147-150` reads right once the tag
  is `@v0.25.0`; `docs/index.md:113,124` (citation) moves to 0.25.0;
  `release-checklist.md:44-45,61-62` cite text no longer in
  `github-action.md`.

## Exception types after #557 (one batch)

- **DOC-1 = LIB-3** maj (library reviewer) / min (docs reviewer), **C**, R.
  The docs say a wrong-type cap raises `ValueError`; #557 raises
  `CodedTypeError` (a `TypeError`): `docs/python-api.md:140-142,149-151,
  330-333,383-384`, `docs/python-api-remote.md:110-112`. Repro:
  `generate(P, max_model_extract_bytes=True)`, `max_download_bytes="5"`,
  `loom.run("g.json", max_dataset_hash_bytes=True)`,
  `loom.run("g.json", pitloom_config=5)`: each `CodedTypeError
  option-invalid`, `isinstance(e, ValueError)` False. `docs/api.md:16-24`
  already states the split.
- **MSG-2** min, **C**, K. The `option-invalid` summary and `did` text
  (`src/pitloom/messages/_options.py:182-210`, generated into
  `docs/message-codes-options.md:24,69,83-90` and both skills'
  `references/messages-options.md`) say the library raises `ValueError` for a
  wrong type. Fix the catalogue text, then regenerate. #557.
- **REG-1** min, **C**, R. `docs/python-api.md:531-534`: a missing
  `loom.run` registry "raises `ValueError`"; it raises
  `CodedFileNotFoundError` (`input-not-found`), as `docs/id-registry.md:41-43`
  says. Repro: `with loom.Run("f.json", id_registry="nope.json")`. #482.

## Message advice per surface (#556 follow-ups)

- **MSG-1** min, **C**, K. `embed_wheel_sbom()` prints `set
  trust_model_files=True` (`messages/_model_stub.py:31`) and `set
  scan_model_usage=True (or set it in pitloom_config)`
  (`messages/_usage_unusable.py:72,100`) but takes neither keyword (the real
  form is `overrides=ConfigOverrides(...)`); passing it is a `TypeError`.
  `generate_wheel_sbom()` takes both. #556.
- **MSG-6** nit, **C**, K. `messages/_file_discovery.py:123` says `pass
  BuildOptions(allow=True)`; every other line says `BuildOptions.allow`
  (`_build.py:91`). #556.
- **MSG-7** nit, **N**, K (by design). Action users read CLI flags, not
  Action inputs (`messages/_surface.py:12-14`).

## Catalogue and message wording

- **MSG-3** min, **C**, K. `docs/python-api-remote.md:102-103`: a fenced
  comment says `generate()` on a PyPI URL logs an `INFO:` naming `loom project
  <url>`; the library line names `generate_pypi_sbom(..., kind='sdist')`. The
  drift tests strip fenced blocks.
- **MSG-4** nit, **C**, K. Stale docstring "naming ``loom model``"
  (`src/pitloom/extract/remote/huggingface.py:233`).
- **MSG-5** nit, **N**, R. `project-not-found` puts a bare quoted path as
  subject, no `DIR=` (`messages/_sbom_target.py:156-158`; #553); and `loom
  project <dir>` names it absolute while `loom generate` names it as typed
  (TRY-9b).

## User docs

- **TRY-2** maj, **C** (doc), R. `docs/python-api.md:314-322`: the
  "evaluation" example (`use_model` + `add_dataset`) records the dataset as
  `trainedOn` (repro: the block as a script; the fragment holds only
  `trainedOn`). `loom.add_validation_dataset()` (in `docs/api.md:99`) gives
  `testedOn` but the page never names it. Pre (the example is in v0.24.0).
  Whether `add_dataset` under `use_model` should mean `trainedOn` at all is a
  question for the user (see the main page).
- **DOC-2** min, **C**, K. `docs/configuration-subtables.md:183-186` says an
  unknown provenance `schema` is caught only at generation; since #524 it is
  `config-invalid` at read.
- **DOC-3** min, **C**, R. `docs/messages.md:45-49`: the `loom:` frame is
  said to be only for errors before the command is known; `loom project .
  --bogus` prints `ERROR: loom: unrecognized arguments: --bogus
  [option-invalid]` (the top-level parser reports a subcommand's leftovers,
  `__main__.py:103`). Fix the wording (cheap) or the frame (next release).
- **TRY-6** min, **B** with TRY-1 (same paragraph), K.
  `docs/fragments.md:169-192` lacks the skill's caveat that an enrichment
  fragment fails `fragment validate` on its own
  (`skills/sbom-validate/SKILL.md:132-137`); the pair then gets no merged
  verdict.
- **DOC-4** nit, **C**, R. `docs/url-credentials.md` has no SPDX header (the
  only page).
- **DOC-5** nit, **C** (docs sweep), R. `docs/python-api.md` is 31,206 bytes,
  over the 30 KB hard limit (27,257 at v0.24.0; grew in #545, #553, #557).
- **DOC-7** nit, **C** (docs sweep), K. After the #549 split,
  `docs/configuration.md` and `docs/python-api.md` have no See-also near the
  top (first pointers at lines 160 and 82).
- **TRY-11** nit, **C** (docs sweep), K. `docs/python-api.md:474` uses an
  undefined `labels`; `:257` "(it raised `FileNotFoundError` before)" is
  history; `docs/id-registry.md:131` names `src/pitloom/core/walk_rules.py`;
  `cli.md:284`/`id-registry-create.md:21` show `id generate data src
  --entity model`, which only says `registry-path-key-unusable`;
  `skills/sbom-generate/references/examples.md:118` `-e
  my-pkg:software_Package` gets `registry-identity-missing`.
- **TRY-9a** min, **C**, R. A version-3 registry gives `ERROR: ... version
  3, expected 4 (no migration support) [registry-wrong-format]` with no
  action; `docs/message-codes-id-registry.md:199-202`, `docs/cli.md:298-299`
  and `docs/id-registry-create.md:93` give three different remedies.

## Skills

- **REG-2** min, **C**, K. `skills/sbom-generate/references/id-registry.md:
  326-331` says loom reads only `id-registry`, `update-id-registry`,
  `max-dataset-hash-bytes` from `pitloom_config`; it also honours
  `url-credentials`/`accept-url-credentials` (`docs/python-api.md:536-539`).
  #494.
- **SKL-3** min, **C**, R. `skills/sbom-generate/references/
  known-limitations.md:310-331` and `sbom-validate/SKILL.md:178-179` say
  `wheel`/`generate` refuse, or "warn first", on a wheel with no single own
  `.dist-info`; they warn (`[dist-info-missing]`) and write the SBOM, exit 0.
  #515.
- **SKL-4** nit, **C**, K. `sbom-generate/SKILL.md:216-217` "an `ERROR:`
  ending `wheel refused`" and `sbom-validate/SKILL.md:117-118` "ends `could
  not be validated`": both lines end in a `[code]`. #515.
- **SKL-5** nit, **C**, R. `references/cli-flags.md:17-19` and
  `SKILL.md:272-274` key "drop the flag next time" on `WARNING: Options:`;
  the build flags print `WARNING: Build: <absolute path>: --no-build-isolation
  has no effect without --allow-build [option-no-effect]` (also the only
  no-effect line with a bare absolute path).
- **SKL-6** nit, **C** (docs sweep), K. Stale `Last-Modified`:
  `sbom-generate/references/examples.md:3`, `build-timeout.md:3`,
  `cli-flags.md:3`.

## GitHub Action

- **ACT-1** min, **N**, K. `action.yml:366-377,610-613` count `embed-wheel`
  matches with `glob.glob`; loom (#491, `cli/commands/utils.py:146-153,
  192-207`) takes a pattern matching nothing as a literal path
  (`dist[1]/x.whl`) and counts regular files once. Repro (reviewer): wheel at
  `dist[1]/demo-1.0-py3-none-any.whl`: `::warning::embed-wheel matches 0
  wheels; ignoring output`, no `sbom-path`, while loom embedded one.
- **ACT-2** min, **N**, K (timing by the reviewer). `action.yml:571`
  `line=${line//'%'/%25}` is quadratic on bash 3.2; credential lines (#489,
  #490) print whole URLs: 10,000 `%` in one URL took 18.5 s user time.
- **ACT-4** nit, **C**, R. `action.yml:585-589` comment "loom emits no
  untagged line": argparse's usage block is untagged (harmless: it comes
  before any tagged line).
- **ACT-5** nit, **C** (docs sweep), K. `docs/github-action.md:3`
  `Last-Modified: 2026-11-23` (changed 2026-11-25, -26).

## Downstream trial, behaviour

- **TRY-1** maj, **B** for a caveat (a documented command fails on the normal
  case), **N** for the fix (pre, upstream), R on both trees. `loom fragment
  validate A B` fails two valid Pitloom SBOMs whose `created` differ: `More
  than 1 values on ... _:CreationInfo0` (sh:MaxCount). The fixture fragments
  (`tests/fixtures/fragments/*.json`) fail it too; `--no-merge` passes; `loom
  merge` output validates. The merged graph is built by spdx3-validate
  (`spdx3_validate.validate(paths, check_merged=True)`,
  `src/pitloom/cli/commands/utils.py:418`), which shares document-scoped blank
  node labels across files. Same in v0.24.0. Upstream (the user's own
  spdx3-validate fork): a handoff, not an edit. For 0.25.0 a caveat at
  `docs/fragments.md:173-182` and `skills/sbom-validate/SKILL.md:121-127` (or
  `--no-merge` by default: a user decision). When only the merged check fails,
  no `FILE=... STATUS=valid` line is printed for the documents that passed
  (`docs/cli.md:364`).
- **TRY-3 = CLI-5** min, **N**, R. `-v` prints `OPTION=creation_datetime
  SOURCE=default VALUE=None` when `SOURCE_DATE_EPOCH` set `created`
  (repro: `SOURCE_DATE_EPOCH=1700000000 loom project p --offline -v`), and
  `OPTION=config_file SOURCE=command-line` with no `--config`.
- **TRY-5** min, **N**, R. `--content-type-method extension` without
  `--content-type` is silently ignored (no `contentType`, no warning);
  `docs/cli-flags.md:86-90` does not say it needs `--content-type`.
- **TRY-7** min, **N** (pre, design question), K. `loom.run` fragments get a
  fresh `uuid4` document namespace every run (`_loom_active_run.py:122`),
  so two runs with a pinned `SOURCE_DATE_EPOCH` differ. Documented
  (`docs/cli.md:280`, `docs/id-registry.md:20`: independent runs get
  different ids; pin them with a registry); the question is CLAUDE.md's "no
  random UUIDs". Builds stay deterministic: they read the saved fragment.
- **TRY-8** min, **N** (pre; arguably wrong SBOM content, a user decision), K.
  `[project.urls] Homepage` is also `software_downloadLocation` when there is
  no `Source` (`assemble/spdx3/_document_main_package.py:51`).
- **TRY-10** (part of CLI-10) nit, **N**, R. `PITLOOM_SBOM_OUTPUT_PATH` is
  relative for `project`'s default name, absolute for
  `wheel`/`model`/`enrich`/`env` defaults (`docs/cli.md:360`).
- **TRY-12** nit, **N**, R. `WARNING: --sbom-basename: a string
  'foo.spdx3.json' is not a bare file name (white space or a trailing
  .spdx3.json); using foo [sbom-name-invalid]` names both causes; a
  hook-table unknown key's traceback ends in the private
  `pitloom.messages._config_say.ConfigError`.
