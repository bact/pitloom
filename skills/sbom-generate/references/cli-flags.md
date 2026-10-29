---
Created: 2026-10-29
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Useful `loom` flags: the full list

See also: `../SKILL.md` ("Flags: what to add, what to leave out", which
holds the rules for the opt-in and unsafe flags); [examples.md](examples.md);
[build-timeout.md](build-timeout.md); [id-registry.md](id-registry.md);
[embed-wheel.md](embed-wheel.md).

Most flags are shared by every generating command (`project`, `generate`,
`wheel`, `model`, `env`, `enrich`, `embed-wheel`); a line names its commands
where they differ, and a flag with no effect on a target logs
`WARNING: Options: ...`.

- `-o FILE` / `--output FILE` -- explicit output path.
- `--config FILE` -- read `[tool.pitloom]` from *FILE* instead of the
  target's own `pyproject.toml`. The only way to give a `wheel`/`env`/
  `model` target, or `enrich`/`embed-wheel` without `--project-dir`, a
  `[tool.pitloom]` at all (they never read the current directory). On a
  project target it replaces the project's own config outright, not merges
  with it.
- `--pretty` -- indent the JSON (default: compact).
- `--offline`/`--no-offline` -- forbid/allow network (`project`, `wheel`,
  `env`, `model`, `embed-wheel`; `generate` follows its target; `enrich` has
  none). On a local model file it has no effect (a `WARNING:`); on a Hugging
  Face model or a Git URL it is an `ERROR:`, as nothing can be fetched.
- `-v` / `--verbose` -- `INFO:` lines: every effective option and its source
  for `project`/`generate` on a project or sdist; the version, target and
  output path for `wheel`/`env`/`model`/`enrich`; a no-effect `WARNING:` on
  `embed-wheel` and `generate` for other targets.
- `--creator-name NAME` (repeatable), `--creator-type TYPE`, `--creator-email
  EMAIL` -- who created the SBOM (BSI: a person or organisation with an
  e-mail); the first creator that is not a `software-agent` is also the main
  package's supplier, never a dependency's or a model's. `--creation-datetime`,
  `--creation-comment`, `--creation-tool`/`--no-creation-tool` set the rest of
  the creation info.
- `--enrich` / `--no-enrich` -- Pitloom's own deterministic, local,
  frontmatter-only enrichment pass, in the same generate call. Add it only
  for a project directory or a local model file: on a wheel, env, sdist
  or Hugging Face target it has no effect and logs a `WARNING:`. See
  "Combine with enrichment or a named standard" in `../SKILL.md`.
- `--extract-file-header` / `--no-extract-file-header` -- per-file SPDX
  header tag scanning (copyright, contributor, licence, file type). On by
  default; cheap, no need to pass it explicitly.
- `--scan-model-usage` / `--no-scan-model-usage` -- record which Python
  files reference each discovered AI model file (`hasDataFile`), on a project
  directory (config key `scan-model-usage`) or a built wheel; other targets
  warn that it has no effect. Off by default and **opt-in only**: add it only
  when the request asks which code loads a model. Models are found either
  way; when the setting was never given, one `INFO:` line names this flag.
- `--allow-signed-wheel` -- `embed-wheel` and `wheel --embed` only; removes a
  `RECORD` signature (see "Signed wheels" in `../SKILL.md`). Never add it
  unless the user agrees.
- `--trust-wheel-model` -- on a built wheel, also read fastText, GGUF, HDF5,
  ONNX and PyTorch `.pt`/`.pth` models, whose readers can crash, hang or
  exhaust memory on a hostile file (else listed without metadata, one
  `INFO:`). Never add it unless the user states the wheel is trusted. Other
  targets and `embed-wheel --project-dir` warn that it has no effect.
- `--content-type` / `--no-content-type` -- per-file content-type/MIME
  detection (`magika`, or a filename-extension guess). Off by default and
  **opt-in only**: add it only when the request implies wanting that data,
  since it costs ~5ms/file with `magika`. `--content-type-method
  {auto,magika,extension}` forces a detector (default `auto`).
- `--build-timeout DURATION` -- with `--allow-build` only; see
  [build-timeout.md](build-timeout.md).
- `--id-registry FILE` -- declare the Loom ID registry for this run.
- `--update-id-registry`/`--no-update-id-registry` -- add newly minted
  ids to the declared registry (on by default; a `WARNING:` where it has
  no effect). Both registry flags: [id-registry.md](id-registry.md).
  `--project-dir DIR` on `wheel`/`project <sdist>` keys their files below
  DIR in a registry rooted above it (reads nothing from DIR).
- `--describe-relationship` (relationship text), `--max-source-metadata-bytes
  N` (cap the `artifact-metadata` annotation; 0, the default, is no cap) and
  `--no-build-isolation` ([build-timeout.md](build-timeout.md)): only when
  asked.
