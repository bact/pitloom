---
Created: 2026-11-26
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Command line flags

See also: [Command line](cli.md) for the subcommands, [Options with no
effect](cli.md#options-with-no-effect), output and debugging, and
[Configuration](configuration.md) for the matching `[tool.pitloom]` keys.

The flags shared by the SBOM subcommands, the flags of the other
subcommands, and the creator and provenance flags.

## Useful flags

Available on `project`/`generate`/`model`/`enrich`/`wheel`/`embed-wheel`/`env`
(not `merge`/`fragment`/`id`, which take only their own flags), unless noted:

- `-o FILE` / `--output FILE` -- explicit output path. With several wheels,
  `embed-wheel` refuses it
  (`--output cannot be used when embedding multiple wheels [option-conflict]`).
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. On a project target (`project`, `generate` on
  a project directory or sdist, `embed-wheel --project-dir`) it replaces the
  project's own config outright, not merges with it. On every other target
  (`wheel`, `env`, `model`, `enrich`, `embed-wheel` without `--project-dir`)
  it is the *only* config that target can get: none of them read the current
  directory or the target's own location. A relative path inside *FILE*
  (`id-registry`, a fragment's `path`) resolves against *FILE*'s directory. A
  missing or invalid *FILE* is an `ERROR:`, except under `embed-wheel --sbom`,
  where it is not read and only warns. The replaced project config is not
  parsed, so `--config` also rescues a project or sdist whose own
  `[tool.pitloom]` is invalid. See [Where settings come
  from](configuration.md#where-settings-come-from) for the precedence table.
- `--pretty` -- indent the JSON (default: compact). Only whitespace between
  tokens is added; key order and values are the compact (RFC 8785) text's.
- `--offline` / `--no-offline` -- forbid network access (PyPI and Hugging
  Face lookups; a Git URL, a PyPI URL or a Hugging Face model target is an
  error, [`offline-unusable`](message-codes-network.md#offline-unusable)), or, with
  `--no-offline`, allow it over a config `offline = true`. Not on `enrich`.
- `--max-download-bytes BYTES` -- the largest file downloaded from a PyPI URL
  (`wheel`, `project` and `generate` with that URL), the most disk a Git
  URL's checkout may take (`project`, `model` and `generate` with that URL),
  and each metadata file of a Hugging Face model, under that file's own cap
  (16 MiB JSON, 1 MiB card, 256 KiB licence) (`model` and `generate`); beats
  `--config`'s `max-download-bytes` (512 MiB by default).
  Over it is an `ERROR:` ([`over-cap`](message-codes-files.md#over-cap)) and no
  SBOM is written; a Hugging Face file over it is left out with a
  `WARNING:` and the rest is read. A
  positive integer: `0` or a negative value exits 2, even where it has no
  effect. Raise it for one run only when you trust the project. See [SBOM from
  a PyPI URL](pypi-urls.md#size-limit).
- `--use-lockfile` / `--no-use-lockfile` -- only on `project`/`generate` (the
  other targets never read a lock file) and `enrich` (for `--project-dir`
  document identity matching, see [Enrich an SBOM](cli.md#enrich-an-sbom)). On by
  default; see [Dependency sources and precedence](dependency-sources.md).
- `-v` / `--verbose` -- on `project`/`generate` with a project directory or
  sdist: log each effective option on stderr as `INFO: OPTION=<name>
  SOURCE=<source> VALUE=<value>` (an sdist's own `pyproject.toml` source is
  its member, e.g. `demo-1.0.0.tar.gz:pyproject.toml`). `wheel`/`env`/`model`/
  `enrich` log `PITLOOM_VERSION`, the target, `OUTPUT_PATH` (`-`: standard
  output; none for `wheel --embed` without `-o`, which writes no copy) and,
  when given, the `PROJECT_DIR` of `enrich` and `wheel`. `generate` on any
  other target and `embed-wheel` warn that `-v` has no effect.
- `--project-dir DIR` -- on `wheel`, and `project`/`generate` with an sdist or
  wheel target: the project directory the archive was built from. With a Loom
  ID registry rooted above the project (a monorepo), the archive's files are
  keyed below DIR's path from the registry's root, as `embed-wheel
  --project-dir` keys them, so they reuse the ids `id generate` or `project`
  recorded. Nothing else is read from DIR. A DIR that is not a directory is an
  `ERROR:`; without a registry, or for a project directory target, it warns
  that it has no effect. See [Monorepo](id-registry-keys.md#monorepo).
- `--id-registry FILE` -- declare a Loom ID registry, taking precedence over the
  target's own `id-registry` key. Nothing is searched for; a declared file
  that is missing, unreadable or invalid is an `ERROR:` and exit 1. See [Loom ID
  registry](id-registry.md).
- `--update-id-registry` / `--no-update-id-registry` -- after generating,
  write newly minted ids back into the declared registry (on by default; no
  effect without one). `model` (and `generate` on a model), `enrich`,
  `embed-wheel` and `wheel --embed` never update a registry and warn that
  the flag has no effect.
- `--describe-relationship` / `--no-describe-relationship` -- include (or
  suppress) human-readable text on SPDX relationships.
- `--extract-file-header` / `--no-extract-file-header` -- scan each source
  file's leading comment header for `SPDX-File*` tags and a per-file
  `SPDX-License-Identifier` (on by default).
- `--content-type` / `--no-content-type` -- detect each file's real content
  type via magika/mimetypes (off by default: real per-file cost).
  `--content-type-method {auto,magika,extension}` picks the detector: `auto`
  tries magika, then an extension guess; `magika` errors at once if magika is
  not installed; `extension` skips magika (stdlib-only).
- `--scan-model-usage` / `--no-scan-model-usage` -- on a project directory
  (`project`, `generate <dir>`, `embed-wheel --project-dir`, and the Hatchling
  hook via the `scan-model-usage` key) or a built wheel (`wheel`, `wheel
  --embed`, `embed-wheel` without `--project-dir`), also record which Python
  files reference each discovered AI model file (`hasDataFile`). Off by
  default: it reads every Python file. AI models are found either way. When
  the setting was never given (no flag, no config key), one `INFO:` line says
  how many were found and names the flag and the `scan-model-usage` key (on a
  wheel, in a `--config` file, as no config is read implicitly there), once
  per `embed-wheel` run. Caps and what it misses: [AI model scan
  limits](ai-model-scan-limits.md).
- `--allow-signed-wheel` -- `embed-wheel` and `wheel --embed`: embed into a
  wheel with a `RECORD` signature by removing the signature. See [Signed
  wheels](wheel-sbom.md#signed-wheels). No `[tool.pitloom]` equivalent.
- `--trust-model-files` -- on a built wheel (`wheel`, `wheel --embed`,
  `embed-wheel` without `--project-dir`) or a Git URL's repository (`project`,
  `model`, `generate`), also read the AI model formats that are otherwise
  listed without metadata there, because a hostile file can crash, hang or
  exhaust memory in their readers. Use it only for files you trust. With
  `embed-wheel --project-dir` the models are read from the project, not the
  wheel. No config key, so no config file can opt in. Which
  formats, and why: [Formats gated in
  wheels](ai-model-scan-limits.md#formats-gated-in-wheels); see also [Settings
  that change the SBOM](ai-model-scan-limits.md#settings-that-change-the-sbom).
- `--max-model-extract-bytes BYTES` -- on the same wheel targets, the
  largest model file copied out to be read (four times it for the wheel);
  beats `--config`'s `max-model-extract-bytes` (512 MiB by default). A
  positive integer: `0` or a negative value exits 2, even where it has no
  effect.
- `--refuse-url-credentials` (also on `merge`, `id generate` and `id import`)
  -- write no SBOM (exit 1) when a URL field value holds a credential; by
  default the SBOM is written with one `WARNING:` per value. Same as
  `url-credentials = "refuse"` in `[tool.pitloom]`; recommended in CI.
  `--accept-url-credential FINGERPRINT` (repeatable, also on `merge`) accepts
  one such value: it is no longer refused, and is warned of more quietly. See
  [Credentials in URLs](url-credentials.md).

`--enrich`/`--no-enrich`: see [Enrich an SBOM](cli.md#enrich-an-sbom).
`--allow-build`/`--no-build-isolation`/`--build-timeout` (only on `project`/
`generate`/`embed-wheel`): see [Building a project to discover its file
list](allow-build.md), an off-by-default, security-relevant opt-in with no
`[tool.pitloom]` equivalent.

## Flags of the other subcommands

These take their own flags, besides the shared ones of [Useful
flags](#useful-flags) where noted (`embed-wheel` takes both):

| Command | Flag | Meaning |
| --- | --- | --- |
| `embed-wheel` | `--sbom FILE` | Embed a pre-generated SBOM instead of generating one; invalid JSON, a non-object or a `.spdx3.json` that is not SPDX 3 is an `ERROR:` |
| `embed-wheel` | `--sbom-basename NAME` | Name of the embedded file under `.dist-info/sboms/`, without extension |
| `embed-wheel` | `--allow-mismatch` | With `--sbom`: embed with a `WARNING:` when its name/version differs from the wheel's |
| `embed-wheel` | `--verify` / `--validate` | Run `verify-wheel` / `validate-wheel` on the result; with `--sbom`, `--validate` checks the file first |
| `verify-wheel` | `--sbom-filename NAME` | The exact file expected under `.dist-info/sboms/` |
| `verify-wheel` | `--fail-on-mismatch` | Exit non-zero (not only `WARNING:`) when the SBOM's name/version differs from the wheel's |
| `validate-wheel` | `--sbom-filename NAME` | The exact file expected under `.dist-info/sboms/` |
| `merge` | `-o FILE`, `--pretty` / `--no-pretty` | Output path and indentation |
| `fragment validate` | `--no-merge` | Validate each document alone, skipping the merged-graph check |
| `fragment list` | `--project-dir DIR` | The project whose configured fragments are listed |
| `id generate`, `id import` | see the linked section | [Pin ids across fragments](cli.md#pin-ids-across-fragments) |

Details: [Wheel SBOMs and PEP 770 embedding](wheel-sbom.md) and [SBOM
fragments](fragments.md).

## Configuration

See [Configuration](configuration.md) for every `[tool.pitloom]` setting, its
default and its CLI/Action/API mapping. Two settings need more explanation.

### Creator and creation metadata

These flags apply to project, AI model and Hugging Face SBOM generation alike.
`--creator-name` is repeatable: each occurrence starts a new creator, in
order. `--creator-type` (`person` default, `organization`, `software-agent`,
`agent`) and `--creator-email` set the type/email of the *most recently named*
creator. `--creation-tool` records *what* produced the SBOM (default
`"Pitloom"`, repeatable; `--no-creation-tool` omits it).
`--creation-comment`/`--creation-datetime` set free-text provenance and an ISO
8601 timestamp. A blank `--creator-name`, `--creator-email` or
`--creation-tool`, a `--creator-type` or `--creator-email` before any
`--creator-name`, and a `--creation-datetime` that is not ISO 8601 are
refused before anything is read (exit 2,
[`option-invalid`](message-codes-options.md#option-invalid)):

```bash
loom project . --creator-name "Alice" --creator-email "alice@example.com"
loom project . --creator-name "Acme Corp" --creator-type organization
loom project . --creator-name "Acme Corp" --creator-type organization --creator-name Alice
loom project . --creator-name "My CI service" --creator-type software-agent
loom project . --creation-datetime "2026-01-15T10:00:00Z" --creation-comment "CI run #123"
```

A `software-agent` creator (a service that runs Pitloom) is the SBOM's author;
it is never the main package's supplier, which stays the first person,
organisation or generic-agent creator, or none.

The same fields can be set in `pyproject.toml`. CLI flags take precedence,
replacing the whole list rather than merging:

```toml
[[tool.pitloom.creator]]
name = "Alice"
email = "alice@example.com"
type = "person"       # or "organization", "software-agent", "agent"

[[tool.pitloom.creator]]
name = "Acme Corp"
type = "organization"

[[tool.pitloom.creation-tool]]
name = "MyCompany SBOM Wrapper"

[tool.pitloom.creation]
creation-datetime = "2026-01-15T10:00:00Z"
creation-comment = "Generated in CI pipeline #123"
```

See [Creation metadata](creation-metadata.md) for what these fields record and
why.

### Metadata provenance

Set by `[tool.pitloom.provenance]` (keys and defaults:
[Configuration](configuration-subtables.md#toolpitloomprovenance); what each does:
[Metadata provenance](metadata-provenance.md)). Of its keys, only
`max-source-metadata-bytes` has a flag, `--max-source-metadata-bytes BYTES`,
to change the byte cap for one run. `--max-model-extract-bytes BYTES` does
the same for `[tool.pitloom] max-model-extract-bytes`, the per-model ceiling
of a wheel's model scan ([AI model scan
limits](ai-model-scan-limits-caps.md#size-and-count-caps)).
