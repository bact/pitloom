---
Created: 2026-09-13
Last-Modified: 2026-11-10
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
- **Remote packages/wheels**: `loom wheel <pypi-url>` and `loom project <pypi-url>`
  are built (0.24.0, iteration 1: see
  [pypi-url-targets.md](../implementation/pypi-url-targets.md)); later
  iterations are in the [roadmap](roadmap.md).
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
   (`sanitize_url()` and `sanitize_url_credentials()` in
   `core/url_masking.py`) are built;
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

## Open design questions

1. **Persistent artefact caching**: Should Pitloom cache remote archives under
   `~/.cache/pitloom/remote/<hash>`, or stay ephemeral by default?
2. **Subdirectory fragment syntax**: `#subdirectory=packages/core` (a page URL
   already names a folder).
3. **Submodule handling**: Should Git submodules be recursively extracted, or
   modelled as independent dependency relationships in SPDX 3?
