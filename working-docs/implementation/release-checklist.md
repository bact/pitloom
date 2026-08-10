---
Created: 2026-08-11
Last-Modified: 2026-08-11
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Release checklist

Steps for cutting a Pitloom release, maintainer-facing. Distinct from
[CONTRIBUTING.md](../../CONTRIBUTING.md)'s per-PR checklist -- this is
the release-cutting process itself, run once per version bump.

## 1. Pre-tag verification (local)

- [ ] `pytest tests/ -q` -- 0 failed.
- [ ] `mypy examples/ src/ tests/` -- clean.
- [ ] `ruff check examples/ src/ tests/` and `ruff format --check
      examples/ src/ tests/` -- clean.
- [ ] `pylint src/ tests/ examples/` -- 10.00/10 (`--ignore-paths` any
      stray local `.venv` under `examples/` -- see
      [summary.md](summary.md) for why one can exist untracked).
- [ ] `claude plugin validate .claude-plugin/plugin.json` and
      `.../marketplace.json` -- both pass.
- [ ] Version string consistent across every file that carries one:
      `pyproject.toml`, `src/pitloom/__about__.py`,
      `.claude-plugin/plugin.json`, `CITATION.cff`, `codemeta.json`,
      `README.md`, `action.yml`, `docs/index.md`. Check with
      `grep -rn "<old-version>"` across those files -- anything left
      over is a missed bump.
- [ ] `CHANGELOG.md`: every merged PR since the last tag either has an
      entry, or is a routine dependabot/CI-only/docs-only/test-only
      change that doesn't need one (cross-check `git log --oneline
      <last-tag>..HEAD | grep "Merge pull request"` against the
      `[#NNN]:` link refs at the bottom of the file).
- [ ] `python -m build --wheel` succeeds locally; the built wheel embeds
      `<name>-<version>.dist-info/sboms/sbom.spdx3.json` (PEP 770).

## 2. Tag and publish

- [ ] Tag the release, push the tag, publish to PyPI (however this
      project's release automation does it -- not scripted here).

## 3. Post-publish verification (the actual published artifact)

Local build success in step 1 checks Pitloom's own build; it does not
prove what PyPI actually serves. Verify the **real, externally-hosted**
wheel directly:

- [ ] Resolve the wheel URL via `https://pypi.org/pypi/pitloom/<version>/json`
      and download it; verify its SHA-256 against the digest PyPI's own
      API publishes for that file.
- [ ] Unzip it and inspect `pitloom-<version>.dist-info/sboms/sbom.spdx3.json`
      directly -- the actual bytes a consumer gets, not a regenerated copy.
- [ ] Confirm PEP 770 location, run schema + SHACL validation
      (`spdx3_validate` or the `sbom-validate` Skill), recompute every
      `software_File`'s SHA-256 from the extracted bytes and cross-check
      against the wheel's own `RECORD`, and confirm the main package's
      PURL/license relationships/creator identity are as expected.
- [ ] Record the result as a new dated entry in
      [wheel-sbom-verification.md](wheel-sbom-verification.md), following
      its existing entries' format -- this is what makes each release's
      verification durable evidence instead of a one-off chat answer
      that disappears with the session that produced it.

## 4. GitHub Release

- [ ] If a draft release already exists for this tag, regenerate its
      notes before publishing -- a draft created early in the release
      window (e.g. right after the first RC) will be missing every PR
      merged since. Don't publish a draft without checking its PR list
      against `git log --oneline <last-tag>..HEAD` first.
