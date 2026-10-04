---
Created: 2026-08-12
Last-Modified: 2026-10-04
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Configuration reference

Every `[tool.pitloom]` setting, its default, and how to reach it from
each surface (CLI flag, GitHub Action input, Python API parameter).
This is the exhaustive reference; [Command line](cli.md) and
[GitHub Action](github-action.md) have narrative walkthroughs with
worked examples for the settings people reach for most (creator/creation
metadata, provenance).

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
as a directory's does; so does one that cannot be read (not valid TOML,
not UTF-8, or over 1 MiB -- a limit for archive members only). The error
names the archive and member, e.g. `config file
dist/demo-1.0.0.tar.gz:pyproject.toml: ...`; `--config` replaces it without reading it. Some keys cannot apply to
an archive and are ignored without a warning:

- `id-registry` (it could only name a file inside the archive) and
  `[tool.pitloom.fragment]` (fragments merge only into a project
  directory's SBOM, even from `--config`);
- `use-lockfile`, `enrich`, `extract-file-header`, `scan-model-usage` and
  `[tool.pitloom.content-type]` -- the settings whose flags warn for an
  sdist (see [Options with no effect](cli.md#options-with-no-effect)).

| Surface | Target's own config | `--config` / `pitloom_config=` | Current directory | Flags |
| :--- | :--- | :--- | :--- | :--- |
| `project`/`generate` (project dir) -- `generate_project_sbom()` | Read | Replaces it | Never read | Override |
| `project`/`generate` (sdist archive) -- `generate_project_sbom()` | Read (root `pyproject.toml`, else `setup.cfg`; not `id-registry`/fragments) | Replaces it | Never read | Override |
| `wheel`/`generate` (`.whl`) -- `generate_wheel_sbom()` | Never read | Only config source | Never read | Override |
| `env`/`generate env` -- `generate_env_sbom()` | Never read | Only config source | Never read | Override |
| `model` (local file)/`generate` -- `generate_model_sbom()` | Never read | Only config source | Never read | Override |
| `model` (Hugging Face) -- `generate_model_sbom()` | Never read | Only config source | Never read | Override |
| `enrich` (no `--project-dir`) -- `enrich_model()` | Never read | Only config source | Never read | Override |
| `enrich --project-dir D` -- `enrich_model(project_target=D)` | Read, for document identity (`use-lockfile`) and the registry (`id-registry`) only; for an sdist D neither applies, but an invalid config still fails the run | Replaces D's own | Never read | Override |
| `embed-wheel --project-dir D` -- `embed_wheel_sbom(project_dir=D)` | Read | Replaces it | Never read | Override |
| `embed-wheel` (no `--project-dir`) -- `embed_wheel_sbom()` | Never read | Only config source | Never read | Override |
| `embed-wheel --sbom` -- `embed_wheel_sbom(sbom_path=...)` | Not read | Not read (`--config` warns, no effect) | Never read | Embedding flags only (`--sbom-basename`, `-o`, `--verify`, ...); every SBOM-generation flag warns, since the file is embedded as is |
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
(`ofline`: `did you mean 'offline'?`). It is not an error, and warns once
per file per run, on every source: `pyproject.toml`, `setup.cfg`, an
sdist's own config (named `archive:member`), `--config` and the Hatchling
hook. It is given before the values are checked, so a misspelt required key
shows its hint ahead of the error. A `setup.cfg` `[DEFAULT]` key is checked
and reported in each section that reads it. Not checked: a misspelt `[tool]`
table (`[tool.pitlom]`), `setup.cfg` sub-section (`[tool:pitloom:provenence]`)
and the hook's own `[tool.hatch.build.hooks.pitloom]` options.

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `pretty` | bool | `false` | `--pretty` / `--no-pretty` | `pretty` | `pretty` | Indent the JSON output with 2 spaces. Not used for an SBOM embedded in a wheel (`embed-wheel`, `wheel --embed`, including its `-o` copy), which is always compact; the flags warn there. |
| `describe-relationship` | bool | `false` | `--describe-relationship` / `--no-describe-relationship` | -- | `describe_relationship` | Include human-readable text on SPDX relationships. Not used for an SBOM embedded in a wheel, as for `pretty`. |
| `sbom-basename` | string | *(derived from project name/version)* | -- | -- | `sbom_basename` | Base filename for the generated SBOM; `.spdx3.json` is added. The extension is optional: one trailing `.spdx3.json` (any case) is dropped with a `WARNING:`, so `x.spdx3.json` gives `x.spdx3.json`. |
| `offline` | bool | `false` | `--offline` | `offline` | `offline` | Skip the PyPI JSON API fallback used to fill dependency metadata gaps. Network attempted, best-effort, by default -- any failure (including no network) silently falls back to local-only data. |
| `use-lockfile` | bool | `true` | `--use-lockfile` / `--no-use-lockfile` | `use-lockfile` | `use_lockfile` | Resolve exact versions from a lock/pin file cascade (`pylock.toml`/`uv.lock`/`poetry.lock`/`pdm.lock`/`Pipfile.lock`/pinned `requirements.txt`) -- see [Dependency sources and precedence](dependency-sources.md). On by default, unlike every other bool above; `false` falls back to direct dependencies and environment introspection only. CLI flag only on `project`/`generate` (dependency resolution) and `enrich` (`--project-dir` document identity matching); no effect on `model`/`wheel`/`embed-wheel`/`env`. |
| `extract-file-header` | bool | `true` | `--extract-file-header` / `--no-extract-file-header` | `extract-file-header` | `extract_file_header` | Scan each source file's leading comment header for SPDX-File\* tags. Independent of content-type detection below -- a binary file with no text header still gets a `contentType` when that's on. |
| `scan-model-usage` | bool | `false` (unset) | `--scan-model-usage` / `--no-scan-model-usage` | `scan-model-usage` | `scan_model_usage` | Record which Python files reference each discovered AI model file (`hasDataFile`); off by default because it reads every Python file. AI models are found either way; when the setting was never given (not even as `false`), one `INFO:` line says how many were found, once per run. Effective on a project directory (`project`, `generate`, `embed-wheel --project-dir`, the Hatchling hook) and a built wheel (`wheel`, `wheel --embed`, `embed-wheel` without `--project-dir`); the flags warn on other targets. A Python file over 1 MiB is skipped with a `WARNING:`. |
| `max-model-extract-bytes` | positive integer | `536870912` (512 MiB) | -- | -- | -- | Largest AI model file copied out of a wheel to be read; a bigger one stays in the SBOM without its metadata, with a `WARNING:`. All models of one wheel together may copy four times this (2 GiB by default); the rest stay without metadata, with one `WARNING:`. See [AI model scan limits](ai-model-scan-limits.md) for the other caps. Zero, negative or not an integer is an error, not "unlimited". A library `PitloomConfig` value is checked on a wheel target and named as `pitloom_config` in the error; a project target ignores the key. Wheel targets only (`wheel`, `wheel --embed`, `embed-wheel` without `--project-dir`), from `--config`/`pitloom_config=`; ignored for a project directory, which is read in place -- but a bad value in a project's own `[tool.pitloom]` is still an error, as the table is validated whenever it is read. |
| `enrich` | bool | `false` | `--enrich` / `--no-enrich` | `enrich` | `enrich` | Run local README/model-card enrichment for discovered AI models. |
| `id-registry` | string | `null`: no registry; nothing is searched | `--id-registry` | -- | `id_registry` | Path to the Loom ID registry file, relative to the project directory (or to the `--config` file's own directory, when set there). Used only when declared here, via `--id-registry`, or via a `--config` file -- never auto-discovered. `loom.Run` is the one exception: it never reads any `[tool.pitloom]` config at all, so it only ever takes its own `id_registry=` kwarg, resolved relative to the current directory. A declared file that's missing, unreadable or invalid raises `ValueError` (CLI: `ERROR:` and exit 1; hook: fails the build). |
| `update-id-registry` | bool | `true` -- from the target's own `[tool.pitloom]` where one applies (see [Where settings come from](#where-settings-come-from)), else from `--config`/`pitloom_config=`, else the default | `--update-id-registry` / `--no-update-id-registry` | -- | `update_id_registry` | After generating, harvest newly-minted ids back into a *declared* registry and save it -- never creates one. Effective on `project`/`wheel`/`env`/`generate`; given for `model`/`enrich`/`embed-wheel`/`wheel --embed` it warns `WARNING: Options: ... has no effect` and is dropped. No effect when no registry is declared -- see [Loom IDs across fragments](https://github.com/bact/pitloom/blob/main/README.md#loom-ids-across-fragments-loom-id). |

**Invalid values / fallback behaviour:** every boolean above raises
`ValueError` at config-read time if set to a non-boolean (e.g. the TOML
string `"true"` instead of the bare value `true`) -- no silent
coercion. `sbom-basename`/`id-registry` raise `ValueError` if set to a
non-string, and `sbom-basename` also if it is a path rather than a file
name (a `/`, `\`, `:` or NUL, or `.`/`..`), or is only `.spdx3.json` --
the same rules as `embed-wheel --sbom-basename`. `extract-file-header` off never errors and never blocks
content-type detection -- see below.

In `setup.cfg`'s `[tool:pitloom]`, where every value is text, a boolean is
`true`/`false`, `yes`/`no` or `1`/`0` (any case) and an integer is base 10;
any other value, or an empty one, raises `ValueError` as above.

**Moved keys:** the pre-rename `ids-file` and `update-registry` keys
raise `ValueError` if present -- e.g. `[tool.pitloom] 'ids-file' has
moved to 'id-registry'. Update your config.` -- rather than being read
under their old names.

## `[tool.pitloom.content-type]`

Content-type detection (`magika`/filename-extension) is independent of
`extract-file-header` above -- both are opt-in, gated separately,
because they have different cost profiles and apply to different kinds
of files (a header only exists in text source; a content type applies
to every file, text or binary).

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `enabled` | bool | `false` | `--content-type` / `--no-content-type` | `content-type` | `content_type` | Detect each file's real IANA media type. Off by default -- `magika` inference is a real per-file cost (~5ms/file). |
| `method` | `"auto"` \| `"magika"` \| `"extension"` | `"auto"` | `--content-type-method` | `content-type-method` | `content_type_method` | Which detector resolves a value: `"auto"` tries `magika`, falling back to a filename-extension guess when `magika` isn't installed or its result is inconclusive; `"magika"` behaves identically per-file but raises immediately if the package isn't installed at all; `"extension"` skips `magika` entirely. |

**Invalid values / fallback behaviour:** `enabled` non-boolean raises
`ValueError` at config-read time. `method` not one of the three listed
values raises `ValueError` at config-read time. `method = "magika"`
with the `magika` package not installed raises `RuntimeError` at
generation time, before any file is scanned -- you asked for `magika`
specifically, so this fails loudly rather than silently degrading every
file's `contentType` the way `"auto"` would. `"auto"`/`"extension"`
never raise for a missing/inconclusive detector; they just resolve to
`None` for that file. Overrides below only ever apply while `enabled`
is `true` -- with it `false`, no file gets a `contentType` at all,
configured overrides or not.

### `[[tool.pitloom.content-type.override]]`

A deterministic, config-asserted `contentType` for files matching a
glob pattern -- pre-empts detection for that file entirely (no
`magika`/extension guess runs). Config-only: no CLI flag, Action input,
or API parameter, since a glob-to-MIME-type mapping doesn't fit a
scalar flag; a caller who wants this programmatically constructs their
own `PitloomConfig`.

| Key | Type | Meaning |
| :-- | :--- | :------ |
| `pattern` | string | A shell-glob (`fnmatch.fnmatchcase`, case-sensitive on every platform) matched against the file's `distribution_path`. `*` matches `/` too, so `vendor/*` matches everything under `vendor/`. |
| `content-type` | string | The MIME/IANA media type to assign on a match, e.g. `"font/woff2"`. |

```toml
[tool.pitloom.content-type]
enabled = true
method = "auto"

[[tool.pitloom.content-type.override]]
pattern = "*.woff2"
content-type = "font/woff2"

[[tool.pitloom.content-type.override]]
pattern = "vendor/*"
content-type = "application/octet-stream"
```

**Invalid values / fallback behaviour:** `override` present but not an
array of tables, an entry not a table, a missing/empty `pattern`, or a
`content-type` not shaped like `type/subtype` -- each raises
`ValueError` at config-read time with a message naming the exact
problem. First-match-wins in declaration order; a file matching no
pattern falls through to normal detection.

## `[tool.pitloom.fragment]`

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `files` | array of strings and/or tables | `[]` | -- | -- | -- | Pre-generated SPDX 3 JSON-LD fragment files merged into a project directory's SBOM (not a wheel, sdist, environment or model file SBOM). Each entry is either a plain path string (shorthand -- every other field below defaults) or an inline table with `path` plus any of the fields below. See [Merge fragments](cli.md#merge-fragments), [`loom fragment list`](cli.md#list-configured-fragments). |

Kept as its own table (rather than folded into a flat `[tool.pitloom]`
key) since it's expected to grow more fragment-related settings.

**`files` table-entry fields** (all optional besides `path`):

| Key | Type | Default | Meaning |
| :-- | :--- | :------ | :------ |
| `path` | string | *(required)* | Path to the fragment file, relative to the directory of the file that sets it (the project directory for its own `pyproject.toml`). |
| `role` | string | `null` | Free-form, unvalidated label for what *part* this fragment plays in a pipeline (e.g. `input_dataset`, `output_dataset`, `ai_model`, `software_package`, `source`, `training_script`, `data_cleaning_script`, `post_processing_script`, `guardrail_safety_function`) -- not enforced, and not read by the merge itself yet; informational only, shown by `loom fragment list`. |
| `description` | string | `null` | Human-readable description of what the fragment covers. |
| `required` | boolean | `false` | If `true`, a missing or unreadable fragment fails the build (`FragmentMergeError`) instead of the default warn-and-skip. |
| `sha256` | string | `null` | Expected SHA-256 hex digest of the fragment file. Currently checked for display only by `loom fragment list` -- not yet enforced before merge (planned: `loom fragment sign`). |
| `link-to-main` | string | `null` | Reserved for a future SPDX relationship type between the fragment's root element and the project's main package. Stored but not yet acted on. |

```toml
[tool.pitloom.fragment]
files = [
    "fragments/legacy.spdx3.json",
    { path = "fragments/model.spdx3.json", role = "ai_model", required = true, sha256 = "a3f1..." },
]
```

## `[tool.pitloom.creation]`

| Key | Type | Default | CLI flag | Meaning |
| :-- | :--- | :------ | :------- | :------ |
| `creation-datetime` | string (ISO 8601) | *(current time)* | `--creation-datetime` | Overrides the SBOM's recorded creation timestamp. |
| `creation-comment` | string | `null` | `--creation-comment` | Free-text comment on `CreationInfo`. |
| `no-creation-tool` | bool | `false` | `--no-creation-tool` | Omit the default `"Pitloom"` creation-tool entry. |

**`creation-datetime` resolution order:** an explicit pin here (or
`--creation-datetime`) always wins when set -- it is a deliberate,
per-SBOM value and so takes priority over the ambient,
workspace-wide [`SOURCE_DATE_EPOCH`][source-date-epoch] environment
variable (reproducible-builds.org). When neither is set, the current UTC
time is used. The same priority order applies to the Hatchling build
hook's `builtTime` field. `SOURCE_DATE_EPOCH` is a useful default for CI
environments that already export it for reproducibility without needing
a per-project `creation-datetime` pin, but an explicit pin always
overrides it.

**Embedding into a wheel (`loom embed-wheel`, `loom wheel --embed`):** a
`.whl` is a ZIP archive, and the ZIP format's own per-entry timestamp
field can only represent dates from 1980-01-01 onward -- a binary format
limitation, unrelated to Unix time (what `SOURCE_DATE_EPOCH` counts from,
starting 1970-01-01) or to the SBOM's own `created` field (plain JSON,
no such limit). A `SOURCE_DATE_EPOCH` set below 1980 (e.g. `0`, a
value some build systems use deliberately as a fixed placeholder) is
floored to `1980-01-01` for the wheel's embedded ZIP entry only -- the
SBOM's own `created` field keeps the true value, so the two can
legitimately diverge. When this happens, Pitloom prints an `INFO:` line
rather than silently rewriting the SBOM's stated creation date to match
the ZIP format's limitation. To avoid the divergence entirely, set
`SOURCE_DATE_EPOCH` to `315532800` (1980-01-01) or later.

[source-date-epoch]: https://reproducible-builds.org/specs/source-date-epoch/

## `[[tool.pitloom.creator]]` / `[[tool.pitloom.creation-tool]]`

Array-of-tables, one entry per creator/tool. See
[Creator and creation metadata](cli.md#creator-and-creation-metadata)
for worked examples and [Creation metadata](creation-metadata.md) for
what these fields record in the generated SBOM.

| Table | Key | Type | Meaning |
| :---- | :-- | :--- | :------ |
| `[[tool.pitloom.creator]]` | `name` | string (required) | Creator's name. |
| | `email` | string | Creator's email. |
| | `type` | `"person"` \| `"organization"` \| `"software-agent"` \| `"agent"` | Defaults to `"person"`. |
| `[[tool.pitloom.creation-tool]]` | `name` | string (required) | Tool name recorded as having produced the SBOM. |

**Invalid values / fallback behaviour:** a missing/empty `name` on
either table, or a non-string `type`/`email`, raises `ValueError` at
config-read time. `--creator-name`/`--creation-tool` on the CLI replace
the whole configured list for that run rather than merging with it.

## `[tool.pitloom.provenance]`

Config-only, except `max-source-metadata-bytes` (see below) -- see
[Metadata provenance](metadata-provenance.md) for what each setting
changes in the generated SBOM's Annotations.

| Key | Type | Default | CLI flag | Action input | API param | Meaning |
| :-- | :--- | :------ | :------- | :------------ | :-------- | :------ |
| `format` | `"annotation"` \| `"comment"` \| `"both"` | `"both"` | -- | -- | -- | How metadata provenance is recorded: SPDX Core `Annotation` elements, legacy `Element.comment` strings, or both. |
| `schema` | string | `"pitloom/1"` | -- | -- | -- | Which statement schema encodes provenance Annotations. |
| `detail` | `"minimal"` \| `"full"` | `"minimal"` | -- | -- | -- | `"minimal"` emits a field-source Annotation only when the source adds signal the native value can't convey; `"full"` emits the per-field source map for every field. |
| `preserve-source-metadata` | `"auto"` \| `"always"` \| `"never"` | `"auto"` | -- | -- | -- | Whether to embed an artifact's verbatim original metadata blob. `"auto"` does so only when the artifact isn't shipped with the distribution (and so can't be re-extracted later). |
| `max-source-metadata-bytes` | `0` or an integer >= 8 | `0` | `--max-source-metadata-bytes` | `max-source-metadata-bytes` | `max_source_metadata_bytes` | Byte budget for the serialised artifact-metadata `Annotation.statement`. `0` means unlimited (today's behaviour). When exceeded, the largest metadata entries are dropped first and the result is marked `truncated`/`truncatedKeys`/`truncatedKeyCount`/`maxMetadataBytes` -- see [Metadata provenance](metadata-provenance.md#size-bounded-preservation). Unlike its siblings above, this one has a CLI flag, an Action input and an API parameter (`generate()`, `generate_*_sbom()`; `ConfigOverrides` for `embed_wheel_sbom()`): a byte cap is an operational knob someone may want to override per-run without editing `pyproject.toml`. |

**Invalid values / fallback behaviour:** a non-string value, or a
`format`/`detail`/`preserve-source-metadata` outside its listed set,
raises `ValueError` at config-read time. An unknown `schema` id is not
caught here (`core` doesn't import the assembly layer's encoder
registry) -- it's caught with a clear error the first time an SBOM is
actually generated. `max-source-metadata-bytes`: only `0` (unlimited) or
at least 8 bytes -- the smallest JSON object it could ever hold -- is
valid. A non-integer, a `bool`, a negative value or 1 to 7 is an error,
never "unlimited": at config-read time, on `--max-source-metadata-bytes`
(exit 2) and on the library's `max_source_metadata_bytes=`.

## See also

- [Command line](cli.md) -- flag-by-flag usage with worked examples.
- [GitHub Action](github-action.md) -- input reference for CI.
- [Python API](python-api.md) -- calling Pitloom from Python code.
- [Dependency sources and precedence](dependency-sources.md) -- how
  resolved lock files feed into Source SBOM dependencies.
- [Hatchling build hook](hatchling-build-hook.md) -- inherits the
  project's `[tool.pitloom]` automatically, no separate hook-level
  config surface (only `[tool.hatch.build.hooks.pitloom] enabled`
  controls whether the hook itself runs).
