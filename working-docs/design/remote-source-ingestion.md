---
Created: 2026-09-13
Last-Modified: 2026-10-20
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Remote source ingestion: `loom project <repo-url>` and remote targets

> **See also**:
> - [roadmap.md](roadmap.md) -- roadmap status and related milestones
> - [metadata-sources.md](metadata-sources.md) -- metadata extraction precedence and cataloger design
> - [lock-files.md](lock-files.md) -- lock-file parsing and dependency cascade
> - [architecture-overview.md](architecture-overview.md) -- overarching SBOM architecture and SPDX 3 model

## Motivation and vision

Currently, `loom project` operates on local directories (`loom project [DIR]`),
while `loom model` supports both local files/directories and remote Hugging Face
repository identifiers (`loom model <hf-repo-id-or-url>`).

In CI/CD workflows, third-party dependency auditing, automated vulnerability
scans, and AI-agent interactions, users frequently need to generate an SBOM
directly from a remote repository or forge without manually cloning the
codebase:

```bash
loom project https://github.com/psf/requests
loom project https://gitlab.com/inkscape/inkscape.git#v1.3.2
loom project git@github.com:owner/repo.git
```

Extending remote target ingestion to other asset types provides architectural
symmetry across Pitloom:
- **Remote projects/repositories**: `loom project <git-url>` (GitHub, GitLab, Codeberg, generic git)
- **Remote AI models**: `loom model <hf-url-or-id>` (already supported via Hugging Face Hub)
- **Remote packages/wheels**: `loom wheel <pypi-url>` or package URL (direct inspection from PyPI or private index)
- **Remote datasets**: `loom dataset <croissant-or-hub-url>`

---

## Architectural role of `pitloom.extract.remote`

To support remote sources cleanly, all network ingestion and platform adapters
are grouped under `pitloom.extract.remote/`:

```
src/pitloom/extract/
├── project/       # Local source-tree parsers (PEP 621, Poetry, setuptools, Flit, PDM)
├── lock/          # Lock-file parsers (poetry, pdm, pylock, uv, pipfile, requirements)
├── ai_model/      # AI model weight & format extractors (safetensors, gguf, onnx, etc.)
├── dataset/       # Dataset metadata extractors (croissant)
└── remote/        # Network ingestion, forge & hub adapters, remote fetchers
    ├── huggingface.py       # Hugging Face Hub API and model card fetcher
    ├── huggingface_fetch.py # Chunked HTTP and caching for Hugging Face
    ├── huggingface_field.py # Hugging Face card metadata parsing
    ├── git.py               # (Planned) Git archive / shallow fetch adapter
    ├── github.py            # (Planned) GitHub REST API adapter (tarball, release, license)
    └── gitlab.py            # (Planned) GitLab REST API adapter
```

### Separation of concerns

1. **`pitloom.extract.remote` is the sole network ingestion boundary**:
   - Handles HTTP/Git network communication, rate limiting, authentication,
     and transient local caching.
   - Enforces the `--offline` policy: every module in `remote/` respects
     offline mode and immediately fails on remote attempts when offline.
   - Sanitizes credentials from URLs and logs (`_sanitize_credentials()`).
2. **Delegation to format extractors**:
   - `remote/` does *not* parse `pyproject.toml`, build configuration, or
     lock files itself.
   - Once a repository tree or archive is acquired, `remote/` passes the local
     path to `pitloom.extract.project.read_project()` and
     `pitloom.extract.lock.apply_locked_dependencies()`.
3. **Upstream provenance capture**:
   - Remote ingestion captures authoritative host and VCS metadata that local
     source trees often lack (commit SHA, canonical repo URL, forge license API
     readings, release tags).

---

## Ingestion pipeline: `loom project <repo-url>`

```mermaid
flowchart TD
    A["CLI: loom project &lt;target&gt;"] --> B{"Is target remote URL?"}
    B -->|No: local path| C["extract.project.read_project(path)"]
    B -->|Yes: remote URL| D{"Is --offline set?"}
    D -->|Yes| E["Abort: TargetRequiresNetworkError"]
    D -->|No| F["remote: Parse URL, host, ref, credentials"]
    F --> G["remote: Resolve auth token (ENV / config)"]
    G --> H["remote: Fetch shallow archive (API tarball or git archive)"]
    H --> I["remote: Extract host/VCS provenance (SHA, tag, API license)"]
    H --> J["Temporary / Cache Workspace"]
    J --> K["extract.project.read_project(workspace)"]
    J --> L["extract.lock.apply_locked_dependencies(workspace)"]
    I --> M["assemble.spdx3.document.build()"]
    K --> M
    L --> M
    M --> N["SPDX 3 JSON-LD Output"]
```

### 1. Target detection and parsing

`pitloom.extract.remote` provides URL detection helpers:
- `is_remote_project_source(target: str) -> bool`: Identifies schemes
  (`https://`, `http://`, `git://`, `ssh://`) and scp-style git URLs
  (`git@github.com:...`).
- `parse_git_target(target: str) -> GitTarget`: Parses URL into base
  repository URL, optional ref/branch/tag (e.g. from `#ref` or `@ref`
  syntax), and optional subdirectory path (for monorepos).

### 2. Retrieval strategy: API tarball vs. shallow Git

To honor Pitloom's resource-efficiency principles (no large unnecessary
downloads, streaming I/O):
- **Primary (Forge API tarball)**: When target is GitHub or GitLab, use their
  archive endpoint (e.g. `GET /repos/{owner}/{repo}/tarball/{ref}`).
  Stream the tarball to a temporary directory without pulling Git history.
- **Secondary (Shallow Git clone / archive)**: For arbitrary git hosts without
  public archive APIs, execute shallow clone (`git clone --depth 1 --branch <ref>`)
  or `git archive --remote`.
- **Cleanup**: Ephemeral workspaces are managed via context managers and purged
  after SBOM generation unless a persistent cache flag is passed.

### 3. VCS and host provenance capture

Remote ingestion produces richer VCS provenance for the SPDX 3 graph:
- **`software_Package.downloadLocation`**: Set to canonical repository URL
  with commit pin (e.g. `git+https://github.com/psf/requests.git@<commit-sha>`).
- **External references**: Emit SPDX `externalRef` of type `vcs` or `git`.
- **Host metadata enrichment**:
  - Forge-detected license (via GitHub/GitLab License API) captured alongside
    in-tree license declarations.
  - Release tag / version correlation.
  - Project description and repository topics/keywords.

---

## Authentication and security

1. **Credential resolution**:
   - Environment variables: `GITHUB_TOKEN` / `GH_TOKEN`, `GITLAB_TOKEN`,
     `NETRC`.
   - CLI / configuration options: `--token` or `[tool.pitloom.remote]`.
2. **Credential sanitization**:
   - Basic-auth credentials in URLs (e.g., `https://user:token@github.com/...`)
     are immediately stripped and moved to Authorization headers.
   - Logs, debug traces, and generated SBOMs must never include raw tokens or
     passwords.
3. **Execution safety**:
   - No arbitrary build code or setup scripts are executed during remote
     ingestion; all project and lockfile extraction remains strictly static.

---

## PyPI package ingestion (`loom pypi <name>[==version]`)

Not built. A PyPI project page or `name==version` becomes an SBOM of that
release, so a consumer (the Lumina web service, an agent, CI) can drop a
PyPI URL and get one without downloading the files itself. Hand-tested on one
small package (2026-10-20): `loom project <sdist>` and `loom wheel <wheel>` each
wrote an SBOM that `sbomcheck` read.

1. **Target**: `https://pypi.org/project/<name>[/<version>]/`, `name`,
   `name==version`. An index URL other than pypi.org is an option, not a default.
2. **Resolve** with the JSON API (`/pypi/<name>[/<version>]/json`). No version
   means the latest release; the chosen version is logged, never silent.
3. **Choose a file**: the sdist (a Source SBOM, `loom project` path); else a
   pure-Python wheel (`py3-none-any`, an Analyzed SBOM, `loom wheel` path); else
   the first wheel for the running platform, said in a `WARNING:`. An option
   picks `sdist` or `wheel`.
4. **Download safely**: only `files.pythonhosted.org` (or the index's file
   host), a size cap and a timeout, chunked reads, the archive limits of the
   sdist and wheel readers, nothing executed (`--allow-build` never applies).
5. **Verify**: the JSON API lists each file's SHA-256; a mismatch is an error,
   a match is recorded on the file element with its source.
6. **What the SBOM says**: the release's declared requirements (`requires_dist`,
   extras as optional), not a resolved environment; the SBOM states so.
7. **Surfaces**: CLI, `generate_project_sbom`/wheel API, skill hand-off; the
   same resolver for all (CLAUDE.md "usage surfaces").
8. **Open**: extras on or off by default; a private index with credentials
   (same token rules as the section above); offline cache of the resolved file.

First consumer: Lumina's *Generate & check* page (a PyPI URL beside a Git or
Hugging Face one), which would call this resolver rather than carry its own.

---

## Usage surfaces

- **CLI**:
  ```bash
  loom project https://github.com/psf/requests
  loom project https://github.com/psf/requests --ref v2.31.0 -o requests-sbom.jsonld
  ```
- **Public Python API**:
  ```python
  from pitloom import generate_project_sbom

  sbom = generate_project_sbom(
      target="https://github.com/psf/requests",
      ref="v2.31.0",
  )
  ```
- **AI Agent Skills**:
  Allows tools like Claude Code or agent runtimes to inspect arbitrary
  external packages and repositories directly without needing a local clone step.

---

## Open design questions

1. **Persistent artefact caching**: Should Pitloom cache remote repository
   archives under `~/.cache/pitloom/remote/<hash>` to speed up repeated runs,
   or remain strictly ephemeral by default?
2. **Monorepo / Subdirectory targets**: Supporting fragments like
   `https://github.com/org/monorepo#subdirectory=packages/core`.
3. **Submodule handling**: Should Git submodules be recursively extracted, or
   modeled as independent dependency relationships in SPDX 3?
