---
Created: 2026-09-13
Last-Modified: 2026-10-21
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

> **Status (2026-10-21):** `loom project <git-url>` and `loom generate <git-url>`
> are built for `http`/`https` Git URLs, by shallow `git` clone on every host
> and not the forge API tarball described below. Not built: tokens, ssh, SBOM
> provenance (`downloadLocation`, VCS references), tarballs, a cache. See
> [remote-git-ingestion.md](../implementation/remote-git-ingestion.md).

## Motivation and vision

`loom project` reads local directories and Git URLs (built); `loom model` reads
local files and Hugging Face identifiers. In CI/CD workflows, third-party
auditing and AI-agent interactions, users need an SBOM from a remote source
without cloning it by hand. The remote targets still open, for symmetry:

- **Private repositories and other transports**: a token for a private
  repository, `ssh://` and scp-style addresses (`git@github.com:owner/repo.git`).
- **Remote packages/wheels**: `loom wheel <pypi-url>` or a package URL (below).
- **Remote datasets**: `loom dataset <croissant-or-hub-url>`.

---

## Architectural role of `pitloom.extract.remote`

All network ingestion lives in `src/pitloom/extract/remote/`: the Git fetcher
(`git.py`, `git_url.py` and helpers) and the Hugging Face modules
(`huggingface*.py`) are built. The forge adapters below are not:

```
remote/
    github.py            # (Planned) GitHub REST API adapter (tarball, release, license)
    gitlab.py            # (Planned) GitLab REST API adapter
```

### Separation of concerns

1. **`pitloom.extract.remote` is the sole network ingestion boundary**: HTTP and
   Git communication, the `--offline` policy and credential sanitisation
   (`sanitize_url_credentials()` in `logging_config.py`) are built;
   rate limiting, token authentication and a transient cache are not.
2. **Delegation to format extractors**: `remote/` does *not* parse
   `pyproject.toml`, build configuration or lock files itself; it hands the
   local path to `read_project()` (built, as in Git URL ingestion).
3. **Upstream provenance capture** (not built): authoritative host and VCS
   metadata that local source trees often lack (commit SHA, canonical repo URL,
   forge licence API readings, release tags).

---

## Not built for Git URLs

The built pipeline is in
[remote-git-ingestion.md](../implementation/remote-git-ingestion.md). Left:

### 1. Forge API tarball

An optimisation: on GitHub or GitLab, stream the archive endpoint
(`GET /repos/{owner}/{repo}/tarball/{ref}`) into a temporary directory without
Git history. It needs one adapter per forge and a token story; shallow `git`
works on every host tested.

### 2. VCS and host provenance capture

- **`software_Package.downloadLocation`**: the canonical repository URL with the
  commit pin (`git+https://github.com/psf/requests.git@<commit-sha>`); today the
  commit is logged, not recorded.
- **External references**: an SPDX `externalRef` of type `vcs` or `git`.
- **Host metadata**: forge-detected licence (GitHub/GitLab licence API) beside
  the in-tree declarations; release tag and version correlation; description
  and topics.

---

## Authentication and security

Built: no arbitrary build code or setup script runs during remote ingestion;
credentials in a URL are stripped from messages. Not built:

1. **Credential resolution**: environment variables (`GITHUB_TOKEN` /
   `GH_TOKEN`, `GITLAB_TOKEN`, `NETRC`); `--token` or `[tool.pitloom.remote]`.
   Today `git`'s own credential helpers apply and nothing is prompted.
2. **Moving URL credentials to Authorization headers.**

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

## Usage surfaces (PyPI target)

CLI (`loom pypi`), the library (`generate_project_sbom`/wheel API) and the
agent skills, through one resolver. The Git URL surfaces are built (see the
status box above).

---

## Open design questions

1. **Persistent artefact caching**: Should Pitloom cache remote archives under
   `~/.cache/pitloom/remote/<hash>`, or stay ephemeral by default?
2. **Subdirectory fragment syntax**: `#subdirectory=packages/core` (a page URL
   already names a folder).
3. **Submodule handling**: Should Git submodules be recursively extracted, or
   modeled as independent dependency relationships in SPDX 3?
