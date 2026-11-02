---
Created: 2026-11-02
Last-Modified: 2026-11-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: verifying a release from the registry's own files (0.22.0)

See also: [README.md](README.md) (index of these notes),
[wheel-sbom-verification.md](../wheel-sbom-verification.md) (the record,
entry "Verification of v0.22.0 (2026-11-02)"),
[release-checklist.md](../release-checklist.md) (step 3, post-publish
verification), [git-lfs-pointers.md](../git-lfs-pointers.md),
[registry-key-must-carry-the-release.md](registry-key-must-carry-the-release.md)
(the version 3 registry refusal tried below),
[ci-cost-and-two-gate-policy.md](ci-cost-and-two-gate-policy.md) (the
pre-release checks this one follows),
[open-research-questions.md](open-research-questions.md).

PR #414 (merged 2026-11-02 12:40 UTC, merge commit `dbf819cd`) added a
dated entry to the verification record for Pitloom 0.22.0. The release was
tagged `v0.22.0` on 2026-10-30 at 16:56:05 UTC (`bdf668d6`, the merge of PR
411) and uploaded to PyPI at 17:05 UTC (the upload time the PyPI JSON API gave
in the entry). The pass ran 2.5 days later, from the files PyPI serves
and nothing else. This note keeps what the pass did, what it found, and
what a pass of this kind cannot see. Numbers are from the entry unless
marked.

## 1. The order of the checks

Each step trusts less of what the previous step trusted.

| Step | Check | Result (entry) |
| --- | --- | --- |
| 1 | Download wheel and sdist from the JSON API's URLs into an empty directory; `sha256sum` against the API's digests | both match; wheel 1,082,575 bytes, sdist 10,351,449 bytes |
| 2 | `RECORD` against the wheel's bytes, row by row and member by member, by a script run with `python -I` | 331 members, 331 rows, 0 bad hashes or sizes, none missing, none extra |
| 3 | The embedded SBOM's `software_File` hashes recomputed from the wheel's bytes, compared with the SBOM and with `RECORD` | 343 elements (325 payload files, 18 directories without a hash); 0 mismatches either way |
| 4 | Fresh Python 3.13 venv, `pip install "pitloom[ai,content-type,validate]==0.22.0"`; `loom verify-wheel --fail-on-mismatch`, `loom validate-wheel`, `spdx3-validate --json` 0.0.7, `scripts/check_sbom_license.py` | all pass; `Pitloom 0.22.0`; `licenseid` 0.6.0 resolved |
| 5 | The installed release on tiny temporary projects: a Git LFS pointer as payload, as `LICENSE`, as a `.gguf`; a version 3 ID registry; `licenseid update --source packaged` | documented behaviour, except the `LICENSE` case (section 2) |
| 6 | The sdist's file list against `git ls-tree -r v0.22.0` | 1,366 tag files plus `PKG-INFO`; 434 tag files left out (`working-docs/`, `.github/`, `.claude-plugin/`, large fixtures, dotfiles); no `.env` or key material |

- **Three hashes, one set of bytes.** Step 3 compares three independent
  sources (the SBOM's recorded digest, a fresh digest of the bytes, the
  `RECORD` row). A mismatch would be localised to one of them; with 0 and 0
  nothing needs localising. The SBOM is then checked against the bytes the
  user receives, not against what the build thought it wrote.
- **Verdicts from Pitloom's own tools and from others.** `verify-wheel`,
  `validate-wheel` and `check_sbom_license.py` are the project's own;
  `spdx3-validate` is a separate tool, but the CI log of run 41449530712
  installs it from a repository under the same GitHub account
  (`git+https://github.com/bact/spdx3-validate.git@0e2e3562`). Whether the
  `validate` extra resolves to the same code was not checked.
- **A registry of version 3 is refused, as decided.** With and without
  `--update-id-registry`: exit 1, no SBOM written, the registry's SHA-256
  unchanged, the two `loom id` commands named in the message. That is the
  D2 ruling of [registry-key-must-carry-the-release.md](registry-key-must-carry-the-release.md)
  seen in the shipped artefact, which a unit test cannot show.

## 2. The finding: a pointer file named as the licence

- **What happened.** A project with `license = {file = "LICENSE"}` where
  `LICENSE` is an unpulled Git LFS pointer records a
  `simplelicensing_SimpleLicensingText` whose text is the file name
  `LICENSE`. No `[lfs-pointer]` line is printed for that file; a DEBUG line in
  `extract/_license_detect.py` is the only trace.
- **How it was found.** The same pass put a pointer in two roles. As
  `tiny/weights.bin` it gave the documented single coded `WARNING:`, listed by
  the pointer's `oid`. As the licence file it gave nothing. A test per feature
  covers the first role; no test seems to have covered the second (*inference*:
  it shipped).
- **What was decided.** The verification entry leaves it a question (whether a
  file name should stand as licence text, "for the maintainer to decide"). The
  known-bugs ledger written the same day takes a position: a file name must
  not stand as licence text; the pointer should give no licence and one
  `WARNING:`, or join the run's pointer summary (entry in
  `working-docs/design/known-bugs/licences-and-licenseid.md`, size S-M, "a
  0.22.1 candidate"). Not fixed in the commit range this note covers.
- **Rejected alternatives.** None recorded.
- **Two smaller findings of the same pass.** A Hatchling file-discovery
  `WARNING:` for a project whose name matches no package directory has no
  `[code]` (not catalogued); `licenseid` has no `--version` option. Both are
  in the entry; the first is a ledger entry
  (`messages-and-provenance.md`).
- **Generalises.** A special input (a pointer, a stub, a placeholder) has one
  handler per role it can play: payload, header, declared licence file,
  dependency file. Pass the same special input through every role in a
  verification pass; the roles that were never listed as roles are where it
  fails silently.

## 3. JSON API and simple index

The JSON API was the source of the digests and URLs in the entry; `pip` reads
the simple index (the HTML or JSON list of files under `/simple/`). A lag
between the two on release day was part of the account given for this round.
The repository entry records neither its size nor its direction, and I found
no log of it: *session record, unverified*.

- **What the pass did cover.** The fresh-venv `pip install ...==0.22.0` in
  step 4 succeeded and reported `Pitloom 0.22.0`, so by 2026-11-02 the simple
  index served the release to `pip`.
- **What it did not.** It did not compare the two sources' digests for one
  file, nor measure when they started to agree.
- Do: take the digest from the source `pip` will use and from the JSON API,
  and compare them; a verifier that reads only the JSON can pass a release
  that `pip` cannot yet fetch, or one whose files differ.

## 4. What a verifier of this kind cannot see

- **Not run (the entry says so):** Merkle root recomputation, the GitHub
  Release assets, attestations and Sigstore bundles, the GitHub Action check.
  The 0.20.2 entry shows the attestation checks were done once before
  (`gh attestation verify`, exit 0 for all three).
- **No rebuild.** The signed release wheel and SBOM are not reproducible:
  `created` and `builtTime` come from the clock (an open P3 entry in
  `working-docs/design/known-bugs/process-tooling-and-release-checks.md`).
  So "these PyPI bytes were built from the tag" is believed on the strength
  of the attestations, not shown by this pass.
- **The sdist is compared by file list.** The method names a list against
  `git ls-tree`; no content comparison is recorded.
- **One interpreter, one platform.** Python 3.13 in a venv; the other
  supported versions and platforms were not installed from PyPI in this pass.
- **Known set of tools judging a known set of outputs.** The checks catch what
  the tools were written to catch. The finding in section 2 came from the
  smoke test, not from any validator: the SBOM with a file name for licence
  text is schema-valid.

## 5. Open

- The pass is manual (release checklist step 3). Whether a post-publish
  workflow could run steps 1 to 4 (they need only the PyPI files) and leave
  the smoke tests and the sdist reading to a person is not decided; no cost
  was estimated.
- How soon after upload a release can be verified without the index lag
  confusing the result is unmeasured.
