---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Pre-release review 0.25.0: findings in the CLI, library, hook, ID registry

See also: [../pre-release-review-0.25.0.md](../pre-release-review-0.25.0.md)
(gates, triage, fix plan), [findings-docs.md](findings-docs.md) (docs,
skills, catalogue, Action, trial; the legend is there).

## Library API

- **LIB-1** maj, **B**, R. `project_dir=""` reads the current directory:
  `embed_wheel_sbom(whl, project_dir="",
  overrides=ConfigOverrides(offline=True))` run inside another project embeds
  that project's `[[tool.pitloom.creator]]` ("Pitloom CI", "Sample Project
  Org") and its "CI Wrapper" tool in the wheel's SBOM;
  `generate_wheel_sbom(..., project_dir="")` and `generate(...,
  project_dir="")` use the cwd as the registry project. The CLI refuses
  `--project-dir ''` (`option-invalid`, exit 2), and this release's CHANGELOG
  says `""` "never reads the cwd" (#545, #550, #557).
  `src/pitloom/embed.py:286-288` (type only),
  `src/pitloom/assemble/_generators_shared.py:61-65` (`Path("").resolve()`).
  `enrich_model(project_target="")` is `input-not-found`, not
  `option-invalid`.
- **LIB-2** maj, **B** (raised by the second opinion), R.
  `loom.add_dataset("")` (and `"  "`) hashes the whole cwd as a dataset named
  `''`: `SHA-256 Merkle root over 2 files ... in dataset directory` (bounded
  by `max_dataset_hash_bytes`, 4 GiB by default).
  `src/pitloom/_loom_args.py:111` has no non-empty rule for `name`.
- **LIB-4** min, **C**, R. `project_dir` of a wrong type: plain `TypeError`
  from `pathlib` on `generate_wheel_sbom()`/`_with_metadata()`; accepted with
  only a no-effect `WARNING:` on `generate_project_sbom()`; refused (coded) on
  `generate()` and `embed_wheel_sbom()`. Same helper as LIB-1.
- **LIB-5** min, **C**, R. `IdRegistry.new(ns, "x.json").save()` (a `str`
  path, which `require_path_argument` accepts) dies with `AttributeError:
  'str' object has no attribute 'parent'` (`id_registry/_format.py:384`);
  `new(path="")` is accepted and fails only at save.
- **LIB-6** min, **C** (PR B: a coded refusal needs `one-of-*` entries in
  `messages/_config_place.py:235-280`), R.
  `generate_git_sbom(sbom_kind="nope")` and `generate_pypi_sbom(kind="egg")`
  raise `InternalError` (`_generators_git.py:146`, `_generators_pypi.py:255`);
  `docs/api.md` says choice arguments are checked. `generate_pypi_sbom("")` is
  `InternalError: url='' is not a url` (`python-api-remote.md:113-114`
  promises `CodedValueError pypi-url-invalid`); `generate_pypi_sbom(None)` is
  `AttributeError` (`_generators_pypi.py:264`).
- **LIB-7** min, **C**, K. The signed-wheel refusal names
  `--allow-signed-wheel` on the library surface
  (`messages/_wheels.py:125`, `_wheels_say.py:135`); #515, missed by #556.
- **LIB-8** min, **C**, R. `IdRegistry` methods, `resolve_registry`,
  `fetch_git_project` and `find_embedded_sbom` never call
  `configure_logging()`: in a fresh process `IdRegistry.load()` of a registry
  with a credential key prints its line through logging's last-resort
  handler, with no `WARNING:` tag and no `[code]` (masked, though).
- **LIB-9** min, **N** (code) and **C** (CHANGELOG), K. Object parameters
  (`pitloom_config`, `creation_metadata`, `credentials`, `provenance`,
  `build_options`, `overrides`, `shown`, `on_merged`) die with a bare
  `AttributeError`/`TypeError` on the generators; `loom.run` checks them;
  `pitloom_config={}` is silently ignored on the wheel, model and enrich
  functions. The #545/#557 CHANGELOG bullet ("loom SDK and library calls
  refuse an argument of the wrong type") overstates this: narrow it to the
  functions `docs/api.md` lists (cheap, PR A).
- **LIB-10** min, **C** (raised by the second opinion), K. A Git URL with no
  host (`https://`) is not refused before `git clone` runs
  (`extract/remote/git.py:298-299` leaves it to later checks; none catches
  it); git then resolved a host `info`. CHANGELOG #491 says such a host is
  "refused before git runs"; the fix is `bool(parts.hostname) and
  host_is_plain(parts)` at `:298`.
- **LIB-11** min, **N** (pre), K. `creation_metadata=` replaces the whole
  creation block (`_generators.py:386`); the CLI's `--creation-datetime`
  keeps the project's creators (`cli/options_resolve.py:174-197`).
- **LIB-12** min, **N**, K. `docs/api.md` omits `generate_pypi_sbom`,
  `PypiSbom`, `find_embedded_sbom`, `CredentialPolicy`, `PitloomConfig`,
  `RemoteFetchPolicy` and others the narrative pages send readers to it for,
  so the #557 test that walks `api.md` does not cover them.
- **LIB-13**, **LIB-14** nits, **N**, K. `loom.run`'s `pitloom_config` and
  `max_dataset_hash_bytes` refusals lack the `loom SDK:` prefix;
  `set_model()` outside a run is an uncoded `RuntimeError` (`loom.py:204`);
  `output_path` annotated `Path | None` though a `str` is accepted;
  `CredentialPolicy(accepted="sha256:...")` (a `str`) does not name the
  parameter.

## ID registry

- **REG-3** min, **C** (with LIB-5), R. `IdRegistry` methods outside
  `load`/`new`/`save(path)` raise uncoded errors: `register(3, "x")`
  `AttributeError`; `register("", "x")` a bare `ValueError` with no code
  (`id_registry/_registry.py:433`, against the catalogue rule);
  `generate(["str"], ...)` `AttributeError`; `IdRegistry(path=3)` accepted;
  `save(Path("."))` a raw `IsADirectoryError` naming the temporary file,
  against `docs/id-registry.md:203-205`. `_registry.py:128-150,433,451,502,
  537,610`. Gap left by #545/#557.
- **REG-4** min, **N** (pre), R. On macOS, `loom id generate <dir>/PTH/src
  --project-dir <dir>/pth` is `PATH ... is outside --project-dir
  [option-invalid]`: `cli/id.py:106-137` uses `Path.relative_to`, then
  `os.path.realpath`, which does not fold case; the registry's `path_key`
  already matches by identity.
- **REG-5** min, **N**, R. `loom id generate . --max-dataset-hash-bytes 3 -e
  data/train.csv:dataset_DatasetPackage` says `INFO: ID registry: dataset
  data/train.csv pinned without SHA-256: FILE=<absolute path>: larger than
  the 3-byte max-dataset-hash-bytes cap; dataset hash omitted
  [registry-hash-missing]`: the run's `[over-cap]` `WARNING:` becomes an
  `INFO:`, the code is lost, the path is absolute and the config key is
  named though the flag was used (`cli/_id_entity.py:80-101,131-145`).
- **REG-6** nit, **N**, R. `version None, expected 4` and `version True`:
  a Python repr in `registry-wrong-format` (`id_registry/_format.py:184-185`).
- **REG-7** nit, **N** (pre), K. `tests/id_registry/test_registry_nfc.py:30`
  holds a literal U+0301, against CLAUDE.md "no invisible or uncommon
  characters".

## Hatchling hook

- **HOOK-1** min, **N** (pre, a7438e92; a lock file ignored by the hook is
  by design, `docs/hatchling-build-hook.md:77-82`, only the silence is a
  defect), K. `[tool.pitloom] pretty = true`
  and `use-lockfile = true` are ignored by the hook without a word:
  `configured_options()` (`core/inert_options.py:348-362`) lists only
  `describe_relationship` and `update_id_registry`. With a `pylock.toml`
  pinning `packaging` 24.0, `loom project` records 24.0 and the hook the
  environment's 26.3 (reviewer repro).
- **HOOK-2** min, **N**, K. An ID registry inside the package
  (`src/demo/ids.json`) is left out of the hook's SBOM though the wheel ships
  it (`plugins/_hatch_document.py:121` `exclude_path`; the reason at
  `core/_models_wheel.py:305-308`, "rewritten after the SBOM", does not hold
  for the hook, which never writes it). Warned (`registry-conflict/file-set`).
- **HOOK-3** min, **N**, K. `plugins/hatch.py:138` creates the staging
  directory outside `coded_write` (`:142`): a failure is an uncoded `ERROR:
  Pitloom build hook: [Errno 13] ...`. Same gap in
  `core/temp_dirs.py:65,88`. #536.
- **HOOK-4** nit, **C** (catalogue text in PR B, the page quote in PR C), K.
  `docs/hatchling-build-hook.md:131-134` quotes `sbom-name-conflict` without
  the `Pitloom build hook:` prefix; the generated
  `message-codes-wheel-sboms.md:51-52` says "exit 1", but only the hook raises
  it and it fails the build (fix in `messages/_wheel_sboms.py:300`). #515.
- **HOOK-5** nit, **N**, K. `unknown keys colour` for one key
  (`messages/_config.py:136`); a `hatch.toml` `[build.hooks.pitloom]` table
  is named `[tool.hatch.build.hooks.pitloom]` (`plugins/_hatch_config.py:22`).
  #497.

## CLI

- **CLI-1** blocker (reported), **B**, R on both trees. `--creator-name ''`
  (or blank) on any generating command ends in a traceback, exit 1:
  `pitloom.messages._emit.CodedValueError: Creator.name: must be a non-empty
  string, got a string ''` (v0.24.0: a bare `ValueError` traceback).
  `cli/parser.py:65` builds `Creator(name=values)` inside an argparse
  `Action`; argparse does not turn the Action's exception into a usage error
  and `parse_args()` (`__main__.py:103`) runs outside `cli_error_handler`.
  Expected `ERROR: loom model: argument --creator-name: ... [option-invalid]`,
  exit 2, as `--creator-email` without a name does.
- **CLI-2** min, **C**, R. `--creation-tool ''`: `ERROR: loom model:
  Tool.name: must be a non-empty string, got a string '' [option-invalid]`,
  exit 1; names the library field, not the flag (#556), and exits 1, not 2
  (`cli/options_resolve.py:166`).
- **CLI-3** min, **C**, R. `fragment validate` on a file named
  `bad<LF>ERROR: forged.json` relays spdx3-validate's text split at the line
  break: `ERROR: loom fragment validate: spdx3-validate: ERROR: forged.json:
  ...`, a second level tag on one line (the frame stays, so no bare line is
  forged). `messages/_sbom_validation_say.py:59-63` `splitlines()`; an ESC in
  the name is quoted instead. #515.
- **CLI-4** min, **N** (pre), R. stdout records put a path that may hold a
  space first: `WHEEL=my demo-0.1-py2.py3-none-any.whl STATUS=failed`
  (`verify_wheel.py:158`, `validate_wheel.py:116`,
  `_embed_wheel_batch.py:71`); `FILE=` and `PATH=` in `fragment.py:80,195`.
  CLAUDE.md: "a value that may hold a space goes last". `WHEEL=` is the
  base name only.
- **CLI-5 = TRY-3** min, **N**, R. `-v`: `OPTION=creation_datetime
  SOURCE=default VALUE=None` when `SOURCE_DATE_EPOCH` set `created`;
  `config_file SOURCE=command-line` for a found `pyproject.toml`; no row for
  `url-credentials`/`accept-url-credentials` (new in #489, #490), `offline`,
  `use_lockfile` or the caps (`cli/verbose.py:67-73,105-116`);
  `docs/cli-flags.md` says it logs "each effective option".
- **CLI-6** min, **N** (code) and **C** (soften the `docs/cli.md` line), K
  (same cause as HOOK-1). `[tool.pitloom] pretty =
  true` is dropped silently by `embed-wheel --project-dir`;
  `core/inert_options.py:351-363` notes only two keys, while `docs/cli.md`
  "Options with no effect" says such a key is noted "the same".
- **CLI-7** min, **N** (pre, needs a ruling), K. A missing local path
  shaped `a/b` is read as a Hugging Face id (`assemble/__init__.py:156`,
  before any local check): `loom generate h/nope -o o.json` and `loom model
  h/nope` reach huggingface.co, warn `401 ... Repository Not Found` and
  `download-network-failed` four times, write an SBOM and exit 0 (reviewer
  run; not re-run, to stay offline). Documented under
  `download-network-failed`, but against "a read/access failure is an error".
- **CLI-8** min, **N** (pre), K. `loom generate env` reads Pitloom's own
  environment even when `./env` is a project directory, with no warning
  (`assemble/__init__.py:150`); `./env` reads the directory.
- **CLI-9** nit, **C** for `''` (silent drop; same Actions as CLI-1), **N**
  for the format check (pre), R. `--creator-email notanemail` is written as an
  `email` identifier with no warning; `--creator-email ''` is dropped
  silently.
- **CLI-10** nit, **N**, R (with MSG-5, SKL-5, TRY-10). Subject and output
  paths absolute on some commands, as typed on others: `loom project <dir>`
  error and `Options:`/`Build:` warnings absolute, `enrich --project-dir`
  and `generate` as typed; `PITLOOM_SBOM_OUTPUT_PATH` relative for
  `project`'s default, absolute for `wheel`, `model`, `env`, `merge`,
  `enrich`. One rule ("as typed") belongs in one helper.
- **CLI-11** nit, **N**, R. An ID registry starting `FF FE` is `not valid
  JSON ... [json-malformed]` (`json.loads(bytes)` reads it as UTF-16);
  `--config`, `--sbom` and `id import` say `file-unreadable/not-utf8`.
- **CLI-12** nits, **N**, R in part. `--accept-url-credential` with 24 hex
  digits echoes `sha256:<16 hex>`; `loom model x --debug` frames as `loom:`
  (DOC-3); `sbom-basename = "a\nb"` is "not a path"; `--sbom-basename a/b`
  exits 1, `''` exits 2; `--max-download-bytes 1_000` and non-ASCII digits
  are accepted (`int()`).
