---
Created: 2026-10-23
Last-Modified: 2026-10-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Target resolution and Package-URL targets (planned for 0.22.0)

See also: [remote-source-ingestion.md](remote-source-ingestion.md) (the remote
targets and what is not built),
[remote-git-ingestion.md](../implementation/remote-git-ingestion.md) (what the
Git target does today), [mlflow-extractor.md](mlflow-extractor.md),
[sbom-format-gaps.md](sbom-format-gaps.md), [roadmap.md](roadmap.md).

> **Status (2026-10-23):** design only, nothing built. Decided: the commit a Git
> URL target was read at is recorded as a `pkg:git` Package-URL (below). Open:
> everything else in [Open questions](#open-questions). Scheduled for 0.22.0.

## Why

Pitloom has three kinds of remote target and will get more:

- a Git URL (repository or page of GitLab, GitHub, Gitea/Forgejo, Bitbucket,
  SourceHut), built;
- a Hugging Face model id or URL, built;
- a PyPI package (`loom pypi <name>[==version]`, designed in
  [remote-source-ingestion.md](remote-source-ingestion.md)), and possibly
  conda packages and MLflow models.

Each is a string the user pastes. A [Package-URL](https://github.com/package-url/purl-spec)
(`pkg:<type>/...`) names the same things without guessing from a host name,
and the SBOM can use one to say what it was made from.

## Today: how a target is chosen

Verified in the code on 2026-10-23.

- `pitloom.assemble._classify_target()` is a first-match ladder of string
  checks returning `env`, `wheel`, `hf`, `git`, `model_file` or `project`.
- `generate()` has a second ladder on those strings, with one row per kind in
  the option tables (`ENV`, `WHEEL`, `HF`, `MODEL_FILE`, `GIT`) that say which
  options apply to it.
- `loom generate` (`cli/commands/generate.py`) has a third: Git and project go
  through `run_remote_project` and `generate_project_from_args`, the rest
  through `generate()`. It can drift from the library.
- `target_is_git_url()` and `target_resolves_to_project()` are public helpers
  tied to two kinds.
- `loom project` and `loom model` also sniff the URL forms they accept.
- Fetchers share no contract: Git is a context manager yielding a local folder
  and a commit (`fetch_git_project`); Hugging Face returns metadata.
- `check_url` (the address policy Lumina relies on), the size cap and the
  timeout are Git-only. A PyPI, conda or MLflow fetcher would need its own
  copy.

A new kind therefore touches: the classifier, `generate()`, the CLI
`generate`, an options row, a subcommand, `_matrix_plan.py`, the skills'
descriptions, and a copy of the URL policy. The surfaces can drift apart
(CLAUDE.md: "a pattern hand-copied across 3+ call sites drifts").

## Package-URL types that matter

From the type definitions in `package-url/purl-spec` (`types/*-definition.json`),
read 2026-10-23. Not checked against Pitloom's code except where noted.

| Type | Namespace and name | Version | Qualifiers | Maps to |
| :--- | :----------------- | :------ | :--------- | :------ |
| `git` | host is the namespace, path is the name; case-sensitive | a git ref, ideally a commit or tag | none | the Git target; no default repository |
| `github`, `bitbucket` | `owner/repo`, lowercased | commit or tag | none | the Git target on a known host (`github.com`, `bitbucket.org`) |
| `huggingface` | `org/model`, case-sensitive | the revision commit hash, lowercase | `repository_url` (default `https://huggingface.co`) | the Hugging Face model target; whether it accepts a revision is unchecked |
| `pypi` | name, lowercased with `-`; no namespace | package version | `file_name` (sdist or wheel), `repository_url` (default `https://pypi.org`) | a fetched archive read by the sdist or wheel reader |
| `conda` | name; no namespace | package version | `channel`, `subdir`, `build`, `type`; default repository `https://repo.anaconda.com` | a fetched archive; needs a conda package reader |
| `mlflow` | model name; no namespace | model version | `repository_url` (the tracking URI, no default), `run_id`, `model_uuid` | an MLflow model ([mlflow-extractor.md](mlflow-extractor.md)); needs a server and probably credentials |

Notes:

- A `pkg:` prefix cannot be confused with a path or a host, unlike the URL forms
  Pitloom guesses at.
- `git`, `github` and `bitbucket` give the host and the ref explicitly, so a PURL
  target needs none of the page-marker heuristics of `git_url.py`.
- A `repository_url` qualifier names a server the user chose, so it goes through
  the same address policy as a Git URL.
- Name rules differ per type (lowercase for `pypi`, `github`, `bitbucket`; case
  kept for `git`, `huggingface`). One normalisation function per type.

## Decided: the commit of a Git URL target is a `pkg:git` identifier

Today a Git URL target is resolved to a repository, a ref and a commit; the
commit is logged and nothing reaches the SBOM (checked on a live SourceHut
repository, 2026-10-23). Decided (user, 2026-10-23): record it with the `git`
PURL type.

Proposed shape, to settle when built:

- `pkg:git/<host>/<path>@<commit>` as an `ExternalIdentifier` of type
  `packageUrl` on the main package, for a Git URL target only (a local folder
  has no remote to name).
- Host and path are those of the repository actually cloned, after redirects,
  with no user name, password or token, and never a temporary path. A folder
  below the root goes in the PURL subpath (`#folder`), as the type's own
  example does.
- Always `pkg:git`, whatever the host: one rule, no per-host mapping. (`github`
  and `bitbucket` PURLs would name the same snapshot; a `pkg:github` form may be
  added if a consumer asks.)
- The branch or tag the URL named is not in the identifier (the version is the
  commit); it can be written in the package's `software_sourceInfo`.
- Format-gaps ledger entry in the same change: `packageUrl` on a package
  identifies a package, and here it names a source snapshot, a second meaning
  ([sbom-format-gaps.md](sbom-format-gaps.md)).
- The main package keeps its `downloadLocation` from `Source`/`Homepage` as now.

Constraints:

- The same URL and commit give the same bytes.
- A test with a `user:SECRET@` URL proves the credentials do not reach the SBOM.
- Same on the CLI (`project`, `generate`), the library
  (`generate_project_sbom`/`generate_git_project_sbom`/`generate`) and Lumina
  (which calls the library); one test per surface and a parity test. No hook
  case.
- The commit is a full 40 or 64 hex digits already (`GitCheckout.commit`).

## Proposed design: one target resolver

Not decided; for 0.22.0 after the open questions are answered. This is a
cross-package refactor: ask before starting it.

- One table of kinds. Each entry: a matcher (string, URL or PURL to a resolved
  target), a fetcher (a context manager yielding a local artefact and the source
  identity), the delegate generator, and its row of applicable options.
- `generate()`, `loom generate` and the public helpers read that table, so the
  library and the CLI cannot drift.
- The address policy, size cap, timeout and offline rule are passed to a fetcher
  once, not rebuilt per source.
- A PURL parser is the first matcher. Git, GitHub, Bitbucket and Hugging Face
  PURLs resolve to the kinds that exist; the existing URL forms become entries
  of the same table.
- A new source (PyPI first) is then one fetcher plus a table row: fetch the
  archive, hand it to the sdist or wheel reader that already exists.
- Subcommands keep their natural inputs (`project`, `model`, `wheel`); URLs and
  PURLs go through `loom generate` and the library. No `loom pypi`, `loom conda`
  unless asked.

## Open questions

1. A `pkg:pypi/<name>@<version>` with no `file_name`: read the wheel (no build,
   has metadata) or the sdist (closer to the source)? Pitloom reads both.
2. One shared network policy object for all fetchers (address check, cap,
   timeout, offline)? Lumina passes `check_url` to Git only today.
3. Does the Hugging Face target accept a revision? A `huggingface` PURL carries a
   commit hash.
4. MLflow: how a tracking server and its credentials are given (nothing is
   prompted; see [mlflow-extractor.md](mlflow-extractor.md)).
5. Conda: a package reader for `.conda` and `.tar.bz2` archives; none exists.
6. Whether a PURL target's own identity also goes into the SBOM (e.g. a
   `pkg:pypi/...` target recorded as the package's identifier) or only the Git
   commit case above does.
7. Name normalisation per type (above); which function is the single source.

## Findings from the 2026-10-23 live checks

Real servers: Bitbucket `zzzeek/sqlalchemy`, SourceHut `~sircmpwn/scm.sr.ht`.

- Fixed (branch `fix-bitbucket-sourcehut-pages`): Bitbucket serves any path below
  a repository as its default branch, so `/branch/<ref>` and `/commits/<sha>`
  were cloned as the plain URL with the ref silently dropped (a "no silent
  deviations" breach). `branch`, `commits`, `commits/branch`, `commits/tag` and
  SourceHut `log` are page markers now. A folder page that names a file
  (Bitbucket `src/`, SourceHut `item/`) reads the folder holding it.
- A Bitbucket repository that does not exist answers like one that needs a
  sign-in (`could not read Username`); that is the server, not a Pitloom bug.
- Fixed (#356), found while cloning `sqlalchemy`:
  untagged stderr lines (`warning: no files found matching '*.js'`,
  `no previously-included files…`) from setuptools's in-process manifest step
  broke the "every stderr line carries a level" rule, on a local checkout too.
  Each is now one `DEBUG:` line. See [known-bugs.md](known-bugs.md).
- Fixed in 0.21.0 (found by a probe): in a project directory, a curated fragment
  `description` for a CRFsuite model lost to the one generated from its labels
  (`Method: generated_from_labels`), with `WARNING: Merge: conflicting
  'description'`. A fragment's value now replaces a generated one; see
  [known-bugs.md](known-bugs.md) and `docs/fragments.md`.
- Still open in Git URL ingestion: DNS-rebinding protection, an imperative
  `setup.py` reader, a short Bitbucket commit id (refused: a server cannot be
  asked for an abbreviated id).

## Steps and size (estimate)

1. Answer the open questions. S.
2. The `pkg:git` identifier on a Git URL target, with its ledger entry and the
   surface tests. S-M. Needs no resolver.
3. The resolver table, moving the existing kinds into it with no behaviour
   change (the manual CLI checks and the surface-parity checks guard that).
   M-L.
4. The PURL parser and the Git, GitHub, Bitbucket and Hugging Face PURLs. M.
5. PyPI fetcher (`loom generate pkg:pypi/...`). M.
6. Conda and MLflow only if asked.

Verification per step: the full suite, the manual CLI checks for `assemble/`,
`extract/` and `__main__.py`, a mutation check per new rule, a Windows dry run
for any path handling, and a fresh read of the skills' descriptions
(`add_parser(` against `skills/*/SKILL.md`).
