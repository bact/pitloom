---
Created: 2026-08-12
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Configuration reference

See also: [Configuration reference, sub-tables](configuration-subtables.md)
for the `[tool.pitloom.*]` sub-tables, and [Command line
flags](cli-flags.md) for the matching flags.

Every `[tool.pitloom]` setting, its default, and how to reach it from
each surface (CLI flag, GitHub Action input, Python API parameter).
This is the exhaustive reference; [Command line](cli.md) and
[GitHub Action](github-action.md) have narrative walkthroughs with
worked examples for the settings people reach for most (creator and
creation metadata).

A CLI flag or API parameter of `None` (its default, when omitted) always
defers to `[tool.pitloom]` where one applies to the target -- see [Where
settings come from](#where-settings-come-from) below, since not every
target has one. Passing an explicit value overrides it for that run
only. A GitHub Action input of `""` (empty, its default) defers the same
way.

## Where settings come from

Precedence, on every surface: a per-run flag/parameter wins over
`--config FILE` (`pitloom_config=`), which wins over the target's own
`[tool.pitloom]` (where one applies), which wins over the hardcoded
default. `--config`/`pitloom_config=` **replaces** the target's own
config outright rather than merging with it -- a key the given file
doesn't set reverts to the default, not to the target's own value. The
replaced config is not parsed at all, so an invalid `[tool.pitloom]` in
the target does not fail a run given `--config`.

Only a project directory, an sdist archive, an `embed-wheel
--project-dir`, and the Hatchling build hook read a target's own
`[tool.pitloom]`. A wheel, an
installed environment, a model file, a Hugging Face model, `enrich`
without `--project-dir`, and `embed-wheel` without `--project-dir` never
read one -- not the current directory's, and not one beside the target --
either could belong to an unrelated project; `--config`/`pitloom_config=`
is the only config they can get.

An sdist archive's own config is read as its unpacked directory's is: the
`[tool.pitloom]` of the `pyproject.toml` at the archive's root, else the
`[tool:pitloom]` of its root `setup.cfg`. An invalid one fails the run,
as a directory's does; so does one that cannot be read (`not valid TOML; ...`,
not UTF-8, or over 1 MiB -- a limit for archive members only). The error
names the archive and member, e.g. `FILE=dist/demo-1.0.0.tar.gz:pyproject.toml:
...`; `--config` replaces it without
reading it. Some keys cannot apply to an archive and are ignored without a
warning:

- `id-registry` (it could only name a file inside the archive) and
  `[tool.pitloom.fragment]` (fragments merge only into a project
  directory's SBOM, even from `--config`);
- `use-lockfile`, `enrich`, `extract-file-header`, `scan-model-usage` and
  `[tool.pitloom.content-type]` -- the settings whose flags warn for an
  sdist (see [Options with no effect](cli.md#options-with-no-effect)).

| Surface | Target's own config | `--config` / `pitloom_config=` | Current directory | Flags |
| :--- | :--- | :--- | :--- | :--- |
| `project`/`generate` (project dir) -- `generate_project_sbom()` | Read | Replaces it | Never read | Override |
| `project`/`generate` (sdist archive) -- `generate_project_sbom()` | Read (root `pyproject.toml`, else `setup.cfg`; not `id-registry`/fragments); `--project-dir`'s never | Replaces it | Never read | Override |
| `wheel`/`generate` (`.whl`) -- `generate_wheel_sbom()` | Never read, nor `--project-dir`'s | Only config source | Never read | Override |
| `env`/`generate env` -- `generate_env_sbom()` | Never read | Only config source | Never read | Override |
| `model` (local file)/`generate` -- `generate_model_sbom()` | Never read | Only config source | Never read | Override |
| `model` (Hugging Face) -- `generate_model_sbom()` | Never read | Only config source | Never read | Override |
| `enrich` (no `--project-dir`) -- `enrich_model()` | Never read | Only config source | Never read | Override |
| `enrich --project-dir D` -- `enrich_model(project_target=D)` | Read, for document identity (`use-lockfile`) and the registry (`id-registry`) only; for an sdist D neither applies, but an invalid config still fails the run | Replaces D's own | Never read | Override |
| `embed-wheel --project-dir D` -- `embed_wheel_sbom(project_dir=D)` | Read | Replaces it | Never read | Override |
| `embed-wheel` (no `--project-dir`) -- `embed_wheel_sbom()` | Never read | Only config source | Never read | Override |
| `embed-wheel --sbom` -- `embed_wheel_sbom(sbom_path=...)` | Not read | Not read (`--config` warns, no effect) | Never read | Embedding flags only (`--sbom-basename`, `-o`, `--verify`, ...); every SBOM-generation flag warns, since the file is embedded as is. `--accept-url-credential` and `--refuse-url-credentials` apply: the file is checked for a credential and embedded unchanged (with a warning) or, in the refuse mode, refused |
| `loom.Run` (script/notebook capture) | Never read | Only config source; only `id-registry`, `update-id-registry`, `max-dataset-hash-bytes`, `accept-url-credentials` and `url-credentials` take effect | Never read | `id_registry=` overrides `id-registry`; `max_dataset_hash_bytes=` overrides `max-dataset-hash-bytes`; `credentials=` adds to `accept-url-credentials`, and its `refuse=True` turns `url-credentials` to `refuse` (never back) |
| Hatchling build hook | Read (always, at build time) | No equivalent -- the hook has no per-run override surface | Never read | None -- no per-run surface |
| GitHub Action | Project and embed-wheel modes read it (`--project-dir` under the hood); model mode never | `config` input maps to `--config` | Never read | Every other input maps to a flag |

A relative path inside a `--config` file (`id-registry`, a fragment's
`path`) resolves against that file's own directory, not the current
directory or a symlink's target -- as a project's own `pyproject.toml`
does. `loom fragment list` reads only the project's own config.
A key a target cannot use is ignored without a warning, since one config
often serves several commands: fragments merge only into a project
directory's SBOM (`project`, `generate <dir>`, `embed-wheel
--project-dir`), and an SBOM embedded in a wheel is always compact. The
matching flags do warn -- see [Options with no
effect](cli.md#options-with-no-effect).
A relative `--id-registry` on the command line resolves against the
current directory, on every command -- unlike a target's own
`id-registry`, which is project-relative.

See [Options with no effect](cli.md#options-with-no-effect) for which
flags a target given for the wrong kind warns about instead of silently
doing nothing.

## `[tool.pitloom]`

A key Pitloom does not know -- in `[tool.pitloom]`, one of its sub-tables
or an entry of `creator`, `creation-tool`, `content-type.override` or
`fragment.files` -- is ignored with one `WARNING:` naming the file, the
table and the key, and either the table that does know it
(`it belongs in [tool.pitloom.provenance]`) or the closest known key
(`unknown key ofline; did you mean offline?`). It is not an error, and warns once
per file per run, on every source: `pyproject.toml`, `setup.cfg`, an
sdist's own config (named `archive:member`), `--config` and the Hatchling
hook. It is given before the values are checked, so a misspelt required key
shows its hint ahead of the error. A `setup.cfg` `[DEFAULT]` key is not
checked: a `[tool:pitloom...]` section inherits it only when the key is one
that section reads, and `[tool:pitloom:content-type:override]` never does.
Not checked: a misspelt `[tool]`
table (`[tool.pitlom]`), `setup.cfg` sub-section (`[tool:pitloom:provenence]`)
and the hook's own `[tool.hatch.build.hooks.pitloom]` options.

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `pretty` | bool | `false` | `--pretty` / `--no-pretty` | `pretty` | `pretty` | Indent the JSON output with 2 spaces (whitespace only; key order stays RFC 8785). Not used for an SBOM embedded in a wheel (`embed-wheel`, `wheel --embed`, including its `-o` copy), which is always compact; the flags warn there. |
| `describe-relationship` | bool | `false` | `--describe-relationship` / `--no-describe-relationship` | -- | `describe_relationship` | Include human-readable text on SPDX relationships. Not used for an SBOM embedded in a wheel, as for `pretty`; the Hatchling hook, which never writes it, notes a key set to `true` here with one `INFO:`. |
| `sbom-basename` | string | *(derived from project name/version)* | -- | -- | `sbom_basename` | Base filename for the generated SBOM; `.spdx3.json` is added. The extension is optional: one trailing `.spdx3.json` (any case) is dropped with a `WARNING:`, so `x.spdx3.json` gives `x.spdx3.json`. |
| `offline` | bool | `false` | `--offline` / `--no-offline` | `offline` | `offline` | Skip the PyPI JSON API fallback used to fill dependency metadata gaps. Network attempted, best-effort, by default -- any failure (including no network) silently falls back to local-only data. A Git URL, a PyPI URL or a Hugging Face model target is the exception: with `offline` true nothing can be fetched, so it is an error, [`offline-unusable`](message-codes-network.md#offline-unusable) ([SBOM from a PyPI URL](pypi-urls.md)); the library honours this key for each of them as the CLI does. |
| `use-lockfile` | bool | `true` | `--use-lockfile` / `--no-use-lockfile` | `use-lockfile` | `use_lockfile` | Resolve exact versions from a lock/pin file cascade (`pylock.toml`/`uv.lock`/`poetry.lock`/`pdm.lock`/`Pipfile.lock`/pinned `requirements.txt`) -- see [Dependency sources and precedence](dependency-sources.md). On by default, unlike every other bool above; `false` falls back to direct dependencies and environment introspection only. CLI flag only on `project`/`generate` (dependency resolution) and `enrich` (`--project-dir` document identity matching); no effect on `model`/`wheel`/`embed-wheel`/`env`. |
| `extract-file-header` | bool | `true` | `--extract-file-header` / `--no-extract-file-header` | `extract-file-header` | `extract_file_header` | Scan each source file's leading comment header for SPDX-File\* tags. Independent of content-type detection below -- a binary file with no text header still gets a `contentType` when that's on. |
| `scan-model-usage` | bool | `false` (unset) | `--scan-model-usage` / `--no-scan-model-usage` | `scan-model-usage` | `scan_model_usage` | Record which Python files reference each discovered AI model file (`hasDataFile`); off by default because it reads every Python file. Where it applies, and the `INFO:` given when it is never set: [`--scan-model-usage`](cli-flags.md#useful-flags); the flags warn on other targets. Its caps: [AI model scan limits](ai-model-scan-limits-caps.md#size-and-count-caps). |
| `max-model-extract-bytes` | positive integer | `536870912` (512 MiB) | `--max-model-extract-bytes BYTES` | `max-model-extract-bytes` | `max_model_extract_bytes` | Largest AI model file copied out of a wheel to be read; one wheel's models together may use four times this. What happens over either: [Size and count caps](ai-model-scan-limits-caps.md#size-and-count-caps); each `WARNING:` ends in [`[over-cap]`](message-codes-files.md#over-cap). Zero, negative or not an integer is an error, not "unlimited", on every surface, even where it has no effect. Wheel targets only (`wheel`, `generate x.whl`, `wheel --embed`, `embed-wheel` without `--project-dir`): the flag or keyword (`generate()`, `generate_wheel_sbom()`; `ConfigOverrides` for `embed_wheel_sbom()`), else `--config`/`pitloom_config=` (a library `PitloomConfig` value is named as `pitloom_config` in the error), else the default. The flag or keyword on any other target warns that it has no effect; a project's own key is ignored there, but a bad value in it is still an error, as the table is validated whenever it is read. |
| `max-download-bytes` | positive integer | `536870912` (512 MiB) | `--max-download-bytes BYTES` | via `config` only | `max_download_bytes` | Largest wheel or sdist downloaded from a PyPI URL, the most disk a Git URL's checkout may take, and each metadata file of a Hugging Face model (under that file's own cap). Over it, the file is not downloaded or the fetch is stopped: `ERROR:` ending in [`[over-cap]`](message-codes-files.md#over-cap), no SBOM (a Hugging Face file: a `WARNING:`, the file left out). The size a server declares never decides this: the bytes received or written do. Zero, negative or not an integer is an error, not "unlimited", on every surface, even where it has no effect. PyPI URL, Git URL and Hugging Face targets only (`wheel`, `project`, `model`, `generate` with such a URL or model id; `generate()`, `generate_wheel_sbom()`, `generate_project_sbom()`, `generate_pypi_sbom()`, `generate_git_sbom()`, `generate_git_project_sbom()` and `generate_model_sbom()` with the URL string or model id): the flag or keyword, else `--config`/`pitloom_config=` (a downloaded project's own key is never read), else the default. The flag or keyword on any other target warns that it has no effect. See [SBOM from a PyPI URL](pypi-urls.md#size-limit) and [SBOM from a Git URL](git-urls-behaviour.md#what-it-does-and-does-not-do). |
| `max-dataset-hash-bytes` | positive integer | `4294967296` (4 GiB) | `--max-dataset-hash-bytes` (`loom id generate` only) | -- (no Action step hashes a dataset) | `max_dataset_hash_bytes` (`loom.Run` only) | Most bytes `loom` reads to hash one dataset, a file or all files of a directory together. Over it, the dataset gets no hash and one `WARNING:` naming this key, ending in [`[over-cap]`](message-codes-files.md#over-cap); sizes are checked first, so such a dataset is not opened. Zero, negative or not an integer is an error, not "unlimited" (exit 2 for the flag). Read by `loom.Run` (`max_dataset_hash_bytes=`, else `pitloom_config=`; a `PitloomConfig` value is named as `pitloom_config` in the error) and by `loom id generate` with `-e` for a dataset (the flag, else the project's own key); every other surface ignores it, but a bad value is still an error wherever the table is read. |
| `enrich` | bool | `false` | `--enrich` / `--no-enrich` | `enrich` | `enrich` | Run local README/model-card enrichment for discovered AI models. |
| `id-registry` | string | `null`: no registry; nothing is searched | `--id-registry` | `id-registry` | `id_registry` | Path to the Loom ID registry file, relative to the project directory (or to the `--config` file's own directory, when set there). Used only when declared here, via `--id-registry`, or via a `--config` file -- never auto-discovered. `loom.Run` reads only an explicit `pitloom_config=`, never a project's `[tool.pitloom]`: its own `id_registry=` argument wins and resolves relative to the current directory; a `pitloom_config=` file's `id-registry` resolves relative to that file's directory. A declared file that's missing raises `FileNotFoundError`, one that's unreadable or invalid `ValueError` (CLI: `ERROR:` and exit 1; hook: fails the build). |
| `update-id-registry` | bool | `true` -- from the target's own `[tool.pitloom]` where one applies (see [Where settings come from](#where-settings-come-from)), else from `--config`/`pitloom_config=`, else the default | `--update-id-registry` / `--no-update-id-registry` | `update-id-registry` | `update_id_registry` | After generating, harvest newly-minted ids back into a *declared* registry and save it -- never creates one. Effective on `project`/`wheel`/`env`/`generate`, and on `loom.Run` (a model declared with `path=`); given for `model`/`enrich`/`embed-wheel`/`wheel --embed` it warns `WARNING: Options: ... has no effect` and is dropped; set to `true` in `[tool.pitloom]`, the Hatchling hook and `embed-wheel --project-dir` (which never write a registry) note it with one `INFO:`. No effect when no registry is declared -- see [Loom ID registry](id-registry.md). |
| `accept-url-credentials` | array of strings | `[]` | `--accept-url-credential FINGERPRINT` (repeatable; adds to the list) | input `accept-url-credentials` (commas or line breaks), `args` or `config` | `credentials=CredentialPolicy(accepted=...)`; `PitloomConfig(accept_url_credentials=...)` | Fingerprints (`sha256:` and 16 to 64 lowercase hex digits) of URL field values that hold a credential and may stay in the SBOM, said with the quieter `accepted` warning; in the `refuse` mode any other such value is refused. A TOML array in `pyproject.toml` or a `--config` file; in `setup.cfg`, `[tool:pitloom] accept-url-credentials` with one fingerprint per line or separated by commas or spaces. `loom merge` and `embed-wheel --sbom` read only the flags. See [Credentials in URLs](url-credentials.md). |
| `url-credentials` | string: `"warn"` or `"refuse"` | `"warn"` | `--refuse-url-credentials` (turns `refuse` on, never off) | input `url-credentials` (`warn` or `refuse`), `args` or `config` | `credentials=CredentialPolicy(refuse=True)`; `PitloomConfig(url_credentials="refuse")` | What a URL field value holding a credential does: `warn` writes the SBOM with one `WARNING:` per value (exit 0; the build hook does not fail the build); `refuse` writes no SBOM (exit 1; the hook fails the build) unless `accept-url-credentials` accepts each value. ID registry keys and file entries follow it too. Any other value is `config-invalid` (`option-invalid` from the library). `setup.cfg`: `[tool:pitloom] url-credentials`. `loom merge` and `embed-wheel --sbom` read only the flag. Recommended in CI: `"refuse"`. See [Credentials in URLs](url-credentials.md). |

**Invalid values / fallback behaviour:** every boolean above set to a
non-boolean (e.g. the TOML string `"true"`) is
[`config-invalid`](message-codes-config.md#config-invalid) -- no silent
coercion. So is a non-string or empty `sbom-basename`/`id-registry` (an
empty `sbom-basename` is no request for the default name: leave the key
out), and an `sbom-basename` that is a path rather than a file name (a
`/`, `\`, `:` or NUL, or `.`/`..`), or is only `.spdx3.json` -- the same
rules as `embed-wheel --sbom-basename`. `extract-file-header` off never errors and never blocks content-type detection -- see below.

In `setup.cfg`'s `[tool:pitloom]`, where every value is text, a boolean is
`true`/`false`, `yes`/`no` or `1`/`0` (any case) and an integer is base 10;
any other value, or an empty one, is `config-invalid` as above.

`setup.cfg` is read as setuptools reads it, with `%` interpolation: write a
literal `%` as `%%` (`description = 50%% faster`), and `%(name)s` stands for
another key's value. A bare `%` or an undefined `%(key)s` in a value Pitloom
reads fails the run, as it fails a setuptools build, with one `ERROR:` naming
the file, section and key. In a section Pitloom does not read (`[bdist_wheel]`),
setuptools' file discovery fails on it: Pitloom warns, naming the section and
key, and writes the SBOM without the file list.

**Moved keys:** the pre-rename `ids-file` and `update-registry` keys
are [`config-moved`](message-codes-config.md#config-moved) (`[tool.pitloom] ids-file:
moved to [tool.pitloom] id-registry`), not read under their old names.

## `[tool.pitloom.content-type]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomcontent-type).

### `[[tool.pitloom.content-type.override]]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomcontent-typeoverride).

## `[tool.pitloom.fragment]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomfragment).

## `[tool.pitloom.creation]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomcreation).

## `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomcreator-toolpitloomcreation-tool).

## `[tool.pitloom.provenance]`

Moved to [Configuration reference, sub-tables](configuration-subtables.md#toolpitloomprovenance).

## See also

- [Command line](cli.md) -- flag-by-flag usage with worked examples.
- [Configuration reference, sub-tables](configuration-subtables.md) -- the
  `[tool.pitloom.*]` sub-tables.
- [GitHub Action](github-action.md) -- input reference for CI.
- [Python API](python-api.md) -- calling Pitloom from Python code.
- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies.
- [Hatchling build hook](hatchling-build-hook.md) -- inherits the
  project's `[tool.pitloom]` automatically, no separate hook-level
  config surface (only `[tool.hatch.build.hooks.pitloom] enabled`
  controls whether the hook itself runs).
