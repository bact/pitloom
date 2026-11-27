---
Created: 2026-11-27
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Library argument validation

See also: [../design/message-consistency-rescan.md](../design/message-consistency-rescan.md)
(section 7: where these gaps were found; section 6: per-surface advice,
#556), [message-catalogue-agent-rules.md](message-catalogue-agent-rules.md).

One rule for a bad argument on every surface: an empty path or file-name
option is `option-invalid` (the CLI exits 2), a library value of the wrong
type a coded `TypeError`, of the right type but refused a coded
`ValueError`, and every `bool` parameter of the documented API takes
`True` or `False` only.

## 1. The gaps

The gaps found by the rescan, probed on main ff26a66a (CLI argv and library
calls):

1. An empty ID registry path: two codes by route (`PitloomConfig(id_registry='')`
   and `IdRegistry.load('')` say `input-not-found`, `save('')`
   `option-invalid`).
2. `--config ''` says `input-not-found` (exit 1); `-o ''` and the other empty
   options `option-invalid` (exit 2). Found with it: `embed-wheel --sbom ''`
   (`input-not-found`), `--sbom-basename ''` (the default name, silently),
   `verify-wheel`/`validate-wheel --sbom-filename ''` (`wheel-sbom-missing`
   `named ''`).
3. Plain `TypeError` from `BuildOptions(allow="false")`, `timeout="90"`
   (`validate_build_timeout`, `core/_models_wheel_types.py`), `IdRegistry.load(b'x')`,
   `refuse_credentials=1`; plain `ValueError` from `IdRegistry.save()` with
   no path.
4. Unvalidated bools: `pretty='false'` writes a pretty SBOM, silently (every
   `bool` keyword of the library, `ConfigOverrides`, `PitloomConfig`). Found
   with it: the loom SDK's `pretty` and `generated` say TOML's `true or false`
   (ruling 12: a library bool says Python's `True or False`).
5. `loom generate ''` (and `' '`) reports the missing `-o` first, not the
   empty target.
6. Input-kind wording: `project directory` (CLI `project`) vs `project path`
   (CLI and library `generate`, `generate_project_sbom()`, `read_project()`)
   for one input, a directory or an sdist archive.
7. `checked_embed_basename(where=)`: each call site picks the surface's
   spelling (the rescan's section 6.2).

## 2. Rulings (as built)

Each ruling had a second opinion (Opus) on the plan and on the code as
first built; its amendments are taken (marked *amended*).

| # | Why | Ruling |
| --- | --- | --- |
| R1 | An ID registry path is always an option's value (`--id-registry`, `-o`, `id-registry`, `id_registry=`, `IdRegistry.load(path)`); no command takes it as its target. `input-not-found` names a target the user pointed at, which `''` is not | `option-invalid` (`must be a non-empty string, got ''`) on every route, raised where the value is first taken: `PitloomConfig(id_registry='')` at construction (`PitloomConfig.id_registry`, a `GivenPath` spelling read too), `IdRegistry.load('')` (`path`, a `CodedValueError`; no caller caught its `FileNotFoundError`). The configuration twin stays `config-invalid` |
| R2 | `pitloom.cli._path_args` states the rule: a path option naming where Pitloom reads or writes refuses `''` as its own error (`option-invalid`, exit 2); a positional target is an input (`input-not-found`, exit 1). `--config`, `--sbom` escaped it; `--sbom-basename ''`, `--sbom-filename ''` took an empty name as the default or as a name | `--config`, `embed-wheel --sbom` take `non_empty_path`; `--sbom-basename`, `--sbom-filename` the new `non_empty_name`. Library twins: `loom.run(pitloom_config='')`, `embed_wheel_sbom(sbom_path='')`, `embed_wheel_sbom(sbom_basename='')`, `find_embedded_sbom(sbom_filename='')`. Positional targets keep `input-not-found`. A test walks every option with a `FILE`/`DIR` metavar or a named file-name option and fails on a plain `type=` |
| R3 | A caller expects `TypeError` for a wrong type; a plain one has no code. The loom SDK already split it (`check_sdk_arguments`) | *amended*: one rule at every `Parameter` stage. A value that fails a type test raises `CodedTypeError`, one of the right type the parameter does not take `CodedValueError`, both `option-invalid` with the value line. The choice is in the shared helper: `invalid_value()` sends an `EXPECTED` id of `TYPE_EXPECTED` (`integer`, `string`, `path`, `python-bool`, `config-source`, ...) to the new `invalid_type()`, which keeps `config-invalid` for a `ConfigPlace`; a check that tested type and value together is split (provenance choices, `content_type_method`, `url_credentials`, `Creator.name`/`.type`, `Tool.name`, `sbom_basename`, `sbom_content`). `CredentialPolicy.refuse` moves with it. A path argument that is no `str` or `os.PathLike` (`generate(5)`, `PitloomConfig(id_registry=5)`) is refused by one helper, `require_path_argument()`, at every library entry taking a path (the reviews found `os.fspath()` or `Path()` raising a plain `TypeError` there, for `output_path` only at the final write, after a wheel or registry was written): targets, `output_path`, `id_registry`, `project_dir`, `project_target`, `IdRegistry.new`/`save` paths; a file name of another type (`sbom_filename=5`) is refused as `file-name`. A wrong type is named by its fixed library spelling (`BuildOptions.timeout`), not through `option_name()`: only a library caller can give one. `IdRegistry.save()` with no path: *amended*, an `ERROR` line of `registry-file-missing` (one cause, one code), `CodedValueError` |
| R4 | A truthy string (`"false"`) must never switch an option on, and `pretty='false'` was silent | Every `bool` (or `bool \| None`) parameter of the documented API (`docs/api.md`, plus `PitloomConfig`) is checked from its annotation: `@checked_bools` (`core/bool_arguments.py`) on each entry point and method, under `@classmethod`, before anything runs (a `ConfigOverrides` check alone is too late: a PyPI URL is handed on first); `check_bool_fields()` in `__post_init__` of `ConfigOverrides`, `PitloomConfig`, `BuildOptions`, `FragmentConfig`, `ContentTypeConfig`, `EnrichConfig`, `RemoteFetchPolicy` (whose `offline` raised an `InternalError`, though `docs/python-api-remote.md` has callers build one). `python-bool` (`True or False`), `CodedTypeError`. *amended*: another spelling of a bool annotation (`Optional[bool]`, `None \| bool`) raises `InternalError` when decorated, never skipped; `typing.get_type_hints` is not used (a `TYPE_CHECKING` import makes it raise). A test walks `docs/api.md` and refuses `"false"` for each bool parameter. The loom SDK's `pretty` and `generated` say `python-bool` |
| R5 | The target is the subject of the run; an empty one makes `-o` moot | *amended*: `loom generate ''` refuses the empty target before the `-o` check; a blank one (`' '`) is left as it was (follow-up below) |
| R6 | One input, one kind; `loom project`'s target may be an sdist archive, which `project directory` misnamed | `project path` for `loom project`'s target; `project directory` stays for `--project-dir` (a directory only) |
| R7 | A call site choosing a surface's spelling is what #556 removed | `checked_embed_basename()` lost `where=`; it names the option through `option_name("sbom_basename")` (`REASON_NAMES`): `--sbom-basename` on the CLI, `sbom_basename` in the library |
| Q1 | An empty name is no request for the default (`None` is); `id-registry = ""` is already refused | `[tool.pitloom] sbom-basename = ""` is `config-invalid` (the CLI, `--config`, the hook fails the build), `PitloomConfig(sbom_basename='')` `option-invalid` |
| Q2 | `project path` misnamed a wheel, a model or an environment given to `loom generate` | A new input kind `target` for `loom generate`'s and `generate()`'s target when nothing tells its kind (empty, blank, or a local path where nothing is); the library now checks a missing project target itself, as the CLI does, so both say `target not found: '<t>'` |

## 3. Surface x input matrix

`now -> after`; `-` the surface has no such input. The GitHub Action runs
the CLI (its inputs are flags; it passes `--config` only when non-empty and
never `--sbom-basename` or `--sbom-filename`), so its column is the CLI's.

| Input | CLI (and Action) | Library | Hook |
| --- | --- | --- | --- |
| ID registry `''` | `--id-registry ''`, `id -o ''`: `option-invalid`, exit 2 (kept) | `id_registry=''` (kept); `PitloomConfig(id_registry='')`: `input-not-found` at use -> `option-invalid` at construction; `IdRegistry.load('')`: `input-not-found` -> `option-invalid`; `save('')`, `new(path='')` (kept); loom `id_registry=''` (kept) | `id-registry = ""`: `config-invalid` (kept) |
| config file `''` | `--config ''`: `input-not-found` exit 1 -> `option-invalid` exit 2 | `loom.run(pitloom_config='')`: `input-not-found` -> `option-invalid` | - |
| external SBOM `''` | `embed-wheel --sbom ''`: `input-not-found` -> `option-invalid` exit 2 | `embed_wheel_sbom(sbom_path='')`: `input-not-found` -> `option-invalid` | - |
| SBOM base name `''` | `--sbom-basename ''`: default name -> `option-invalid` exit 2; `sbom-basename = ""` in `--config` or the project: default -> `config-invalid` | `embed_wheel_sbom(sbom_basename='')`, `PitloomConfig(sbom_basename='')`: default -> `option-invalid` | `sbom-basename = ""`: default -> `config-invalid` (the build fails) |
| SBOM file name `''` | `--sbom-filename ''`: `wheel-sbom-missing` -> `option-invalid` exit 2 | `find_embedded_sbom(sbom_filename='')`: `None` -> `option-invalid` | - |
| bool | argparse (never a string) | every documented bool parameter and field: silent, or a plain `TypeError` (`BuildOptions`, `IdRegistry`) -> `option-invalid` `CodedTypeError` | TOML type (`config-invalid`, kept) |
| other wrong types | argparse | `BuildOptions(timeout='90')`, `IdRegistry.load(b'x')`: plain `TypeError` -> `CodedTypeError`; `CredentialPolicy(refuse=1)`, `max_download_bytes='9'`, `provenance_format=5`, `content_type_method=5`, `url_credentials=5`, `Creator(name=5)`, `Tool(name=5)`, `sbom_basename=5`, `loom.run(pitloom_config=5)`: `CodedValueError` -> `CodedTypeError`; `embed_sbom_in_wheel(sbom_content=5)`: `AttributeError` -> `CodedTypeError` | `config-invalid` (kept) |
| path of another type | argparse (always a string) | `output_path=5` (a plain `TypeError` at the final write, after the wheel or registry was written), `id_registry=5`, `project_dir=5`, `IdRegistry.new(path=5)`, `save(5)`, `embed_sbom_in_wheel(5, ...)`, `generate(5)`, `generate_project_sbom(5)`, `generate_wheel_sbom(5)`, `embed_wheel_sbom(5, sbom_path=5)`, `generate_model_sbom(5)`, `enrich_model(5)`, `generate_merged_sbom(5)`, `PitloomConfig(id_registry=5)`: plain `TypeError` from `os.fspath()` (or none until use) -> `CodedTypeError` | TOML type (`config-invalid`, kept) |
| no registry path | - | `IdRegistry.save()` with none: plain `ValueError` -> `registry-file-missing` | - |
| empty `generate` target | `loom generate ''` without `-o`: `option-missing` -> `input-not-found` | `generate('')`: `input-not-found` (kept) | - |
| missing `generate` target | `project path not found` -> `target not found` | `project path` -> `target` | - |
| `loom project` target kind | `project directory` -> `project path` | `project path` (kept) | - |
| embed base name spelling | `--sbom-basename` | `sbom_basename` (from the surface, not the call site) | - |

## 4. Ruled out or left, with the reason

- `IdRegistry.lookup()` and `IdRegistrySession.lookup_key()` are decorated
  too (documented API); the check reads two names per call, negligible
  beside the lookup itself.
- `PitloomConfig` is not frozen: `cfg.pretty = "false"` after construction
  skips the field check. A config built in code is checked when built, as
  `loom.Run` checks its arguments; a later assignment is the caller's.
- The reference page's ERROR rule for `registry-file-missing` says the
  ERROR is the library's only (`ERROR_RULE_OVERRIDES`), not a command's
  exit 1.
- Follow-ups (outside this change): a blank target (`loom generate ' '`,
  `generate(' ')`) is refused as `not found` although a directory named
  `' '` may exist (`loom project ' '` reads it);
  `generate_project_sbom(pitloom_config='')` (any non-`PitloomConfig`)
  dies with a bare `AttributeError`, as do the other object-typed
  parameters (`creation_metadata=`, `provenance=`, `credentials=`,
  `build_options=` given `5`); `generate_git_sbom(5)` raises a plain
  `TypeError` from `re`; `CreationMetadata(creators=5)` is accepted;
  `docs/api.md` therefore names the argument kinds checked, not all; the text options (`--creator-name ''`,
  `--creation-comment ''`) take an empty value as given; the other
  `LIBRARY_SITES` raises (`register()` with an empty type name,
  `_require_names`, `scalar_text`) stay uncoded.

## 5. Gates

- Gate A: full suite (`-n 4`); ruff, pylint (`examples/ src/ tests/
  tests/*/`, 10.00), mypy, pyright, pyrefly, flake8, bandit; message
  inventory and reference `--check`; each new regression test fails on
  the base tree (`git archive HEAD`, `PYTHONPATH` pinned); CLI probes on
  base and tree.
- Mutation: 35 mutants of the new checks (23, then 12 for the round-2
  path checks) (`bool_arguments`, the
  type/value routing, each empty-value and wrong-type check, the
  `generate` order and kinds), all killed; the one survivor at first
  (`generate()`'s own missing-target check) got a library test.
- Review: two fresh-context Opus rounds; round 1 found the plain
  `TypeError` of a non-path value (now `require_path_argument()`) and
  stale docstrings; round 2 the same for `output_path`, `id_registry`,
  `project_dir` and the registry's own paths, a file name of another
  type, `RemoteFetchPolicy.offline` (an `InternalError`, now
  `check_bool_fields()`) and an over-broad `docs/api.md` claim.
