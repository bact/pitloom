# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The probe corpus of the credential detector: values with planted secrets
(``S3CRET``, ``T0KEN``), values that only look like they hold one, and prose
the detector must never refuse.

See also: test_url_masking_detect.py (the tests that read it).

Each row is ``(id, text, strip_changes, refused)``. *strip_changes* is
whether the SBOM strip (``pitloom.export._spdx3_strip``, to be retired in
PR 2) changed the text, computed once on the tree before the detector.
*refused*
is whether the detector refuses it (an account name accepted), reviewed row
by row. The detector reads a URL-typed value as a whole and no prose: every
text the strip changed is refused, except a ``prose-`` row (a sentence that
mentions a URL, a token or an address), which is never refused.
"""

from __future__ import annotations

from urllib.parse import quote

#: The secrets planted in the corpus.
PLANTED = ("S3CRET", "T0KEN")


def encoded(text: str, depth: int) -> str:
    """*text* percent-encoded *depth* times (no character kept)."""
    for _ in range(depth):
        text = quote(text, safe="")
    return text


def marks(count: int) -> str:
    """A URL whose first parameter value holds *count* ``?``."""
    return "https://h.example/x?q=" + "1?q=" * count + "1"


def b62(length: int) -> str:
    """A token body of *length* base-62 characters holding ``T0KEN``."""
    return ("T0KEN" + "aB3" * 60)[:length]


_URL = "https://u:S3CRET@h.example/x"
_HF = "Tq" * 17
_SLACK = "1234567890-1234567890-"
_OPENAI = f"{b62(58)}T3BlbkFJ{b62(58)}"
#: Each token prefix and (the body of its shortest real shape, a near-miss
#: body that is none), after the gitleaks rule set.
TOKENS: dict[str, tuple[str, str]] = {
    **{f"gh{kind}_": (b62(36), b62(35)) for kind in "porsu"},
    "github_pat_": (f"{b62(22)}_{b62(59)}", f"{b62(22)}_{b62(58)}"),
    **{
        f"{kind}-": (b62(20), b62(19))
        for kind in ("glpat", "gldt", "glrt", "glcbt", "gloas")
    },
    "glptt-": ("0f" * 20, "0f" * 19 + "0"),
    "xoxb-": ("1234567890-1234567890", "1234567890-123456789"),
    **{f"xox{kind}-": (_SLACK + b62(8), _SLACK + b62(7)) for kind in "pe"},
    **{f"xox{kind}-": (f"1-2-{b62(8)}", f"1-2-{b62(7)}") for kind in "ar"},
    **{f"xox{kind}-": ("1-2-3-a", "1-2-3-") for kind in "os"},
    **{f"xoxe.xox{kind}-": (f"1-{b62(163)}", f"1-{b62(162)}") for kind in "bp"},
    "xapp-": ("1-A0T0KEN12-1234567890-abc12345", "1-A0T0KEN12-1234567890-abc1234"),
    "hf_": (_HF, _HF[:-1]),
    "api_org_": (_HF, _HF[:-1]),
    "AKIA": ("T2KENABCDEFGHIJK", "T2KENABCDEFGHIJ"),
    "ASIA": ("T2KENABCDEFGHIJK", "T0KENABCDEFGHIJK"),
    "pypi-": ("AgE" + b62(50), "AgE" + b62(49)),
    "npm_": (b62(36), b62(35)),
    **{
        f"sk-{kind}-": (_OPENAI, f"{b62(57)}T3BlbkFJ{b62(58)}")
        for kind in ("proj", "svcacct", "admin")
    },
    **{
        prefix: (f"{b62(93)}AA", f"{b62(92)}AA")
        for prefix in ("sk-ant-api03-", "sk-ant-admin01-")
    },
    "AIza": (b62(35), b62(34)),
}
_IN_URL = "https://h.example/x?q="

#: (id, text, whether the strip changed it, whether it is refused).
PROBES: tuple[tuple[str, str, bool, bool], ...] = (
    ("empty", "", False, False),
    # User information.
    ("ui-basic", _URL, True, True),
    ("ui-user", "https://T0KEN@h.example/x", True, True),
    ("ui-quote", "https://o'brien:S3CRET@h.example/x", True, True),
    ("ui-space", "https://x y:S3CRET@h/x", False, True),
    ("ui-two-at", "https://u:S3CRET@x@h.example/x", True, True),
    ("ui-break", "https://u:S3CRET?x@h.example/r", True, True),
    ("ui-collapsed", "https:/u:S3CRET@h.example/x", True, True),
    ("ui-http", "http://u:S3CRET@h.example/x", True, True),
    ("ui-lead-space", f"  {_URL}", True, True),
    ("ui-ssh-pw", "ssh://git:S3CRET@h.example/r", True, True),
    ("ui-ssh-token", "ssh://ghp_T0KEN@h.example/r", True, True),
    ("ui-ssh-acct", "ssh://git@h.example/r", False, False),
    ("ui-empty", "https://@h.example/x", False, False),
    ("ui-mail-query", "https://h.example?contact=me@x.org", False, False),
    ("ui-port-query", "https://h.example:8080?x=a@b", False, False),
    ("ui-nested-url", f"https://h.example/r?to={_URL}", True, True),
    # Schemes a masker reads after one separator or backslashes.
    ("wide-s3", "s3:/u:S3CRET@h.example/x", False, True),
    ("wide-git-https", "git+https:/T0KEN@h.example/x", False, True),
    ("wide-ssh-bs", "ssh:\\\\u:S3CRET@h.example/x", False, True),
    ("wide-git-bs", "git:\\\\u:S3CRET@h/x", False, True),
    ("wide-s3-query", "s3:/h.example/x?access_token=S3CRET", False, True),
    ("wide-path", "/x/T10:/a@b", False, False),
    ("wide-drive", "C:\\x\\a@b", False, False),
    # Secret-named query values.
    ("q-token", "https://h.example/x?token=T0KEN", True, True),
    ("q-api-key", "https://h.example/x?api_key=T0KEN&a=1", True, True),
    ("q-password", "https://h.example/x?password=S3CRET", True, True),
    ("q-access-key", "https://h.example/x?access_key=T0KEN", True, True),
    ("q-signature", "https://h.example/x?signature=T0KEN", True, True),
    ("q-amz", "https://b.example/k?X-Amz-Signature=T0KEN&X-Amz-Date=1", True, True),
    ("q-session-id", "https://h.example/x?session_id=T0KEN", True, True),
    ("q-fragment", "https://h.example/x#access_token=T0KEN", True, True),
    ("q-enc-name", "https://h.example/x?t%256Fken=T0KEN", True, True),
    ("q-space-path", "https://h/a b?token=T0KEN", False, True),
    ("q-no-scheme", "/x/y?token=T0KEN", False, False),
    ("q-state", "https://h.example/x?state=T0KEN", False, False),
    # Weak names, alone and nested.
    ("w-code", "https://h.example/x?code=1", False, False),
    ("w-sort-key", "https://h.example/x?sort_key=V", False, False),
    ("w-nested-weak", "https://h.example/x?code=1?session=2", False, False),
    ("w-nested-secret", "https://h.example/x?code=1?token=T0KEN", True, True),
    # PEP 508 requirements with a direct reference, as a whole value.
    ("req-space", "name @ https://u:S3CRET@h.example/x.whl", True, True),
    ("req-nospace", "name@https://u:S3CRET@h.example/x.whl", True, True),
    ("req-quote", "name @ https://o'brien:S3CRET@h.example/x.whl", True, True),
    ("req-quote-ns", "name@https://o'brien:S3CRET@h.example/x.whl", True, True),
    (
        "req-marker",
        'n[a,b] @ https://h.example/x.whl?token=T0KEN ; python_version>"3"',
        True,
        True,
    ),
    ("req-clean", "name @ https://h.example/x.whl", False, False),
    # scp-style addresses, as a whole value.
    ("scp-pw", "alice:S3CRET@host.example:o/r", True, True),
    ("scp-account", "git@host.example:o/r", False, False),
    ("scp-dotless", "alice:S3CRET@host:repo", False, True),
    ("scp-build", "build:42@ci:linux", False, True),
    ("scp-image", "python:3.11@sha256:abc", False, False),
    # PURL qualifiers, plain and percent-encoded.
    ("purl-plain", f"pkg:generic/x?download_url={_URL}", True, True),
    ("purl-enc1", f"pkg:generic/x?download_url={encoded(_URL, 1)}", True, True),
    ("purl-enc2", f"pkg:generic/x?download_url={encoded(_URL, 2)}", True, True),
    ("purl-enc5", f"pkg:generic/x?download_url={encoded(_URL, 5)}", True, True),
    ("purl-enc6", f"pkg:generic/x?download_url={encoded(_URL, 6)}", False, True),
    ("purl-upper", f"PKG:generic/x?download_url={encoded(_URL, 1)}", True, True),
    (
        "purl-enc-token",
        "pkg:generic/x?download_url=" + encoded("https://h.example/x?token=T0KEN", 1),
        True,
        True,
    ),
    ("purl-scp", "pkg:generic/x?vcs_url=alice:S3CRET@host.example:o/r", True, True),
    ("prose-in-purl", "pkg:generic/x?note=see%20" + encoded(_URL, 1), True, False),
    (
        "purl-clean",
        "pkg:generic/x@1.0?checksum=sha256:abc&download_url=https://h.example/x",
        False,
        False,
    ),
    ("purl-hf", "pkg:huggingface/o/n@abc", False, False),
    ("purl-subpath-url", "pkg:pypi/x@1?a=b#sub/" + _URL, True, True),
    ("purl-subpath-scp", "pkg:pypi/x@1?a=b#alice:S3CRET@h:x", False, True),
    ("purl-subpath-bare", "pkg:pypi/x@1#sub/" + _URL, True, True),
    ("purl-subpath-enc", "pkg:pypi/x@1#sub/" + encoded(_URL, 1), False, True),
    ("q-next-scp", "https://h.example/x?next=alice:S3CRET@host:o/r", False, True),
    # Query nesting.
    ("marks-16", marks(16), False, False),
    ("marks-17", marks(17), True, True),
    # Token shapes inside a URL value.
    *((f"tok-{p}", f"{_IN_URL}{p}{b}", False, True) for p, (b, _) in TOKENS.items()),
    ("tok-encoded", f"{_IN_URL}Bearer%20ghp_{b62(36)}", False, True),
    # URL values whose path only looks like a token.
    ("near-ghp-35", f"{_IN_URL}ghp_{b62(35)}", False, False),
    ("near-ghp-37", f"{_IN_URL}ghp_{b62(37)}", False, False),
    ("near-akia-15", f"{_IN_URL}AKIAT2KENABCDEFGHIJ", False, False),
    ("near-akia-17", f"{_IN_URL}AKIAT2KENABCDEFGHIJKL", False, False),
    ("near-akia-digit", f"{_IN_URL}AKIAT0KEN12345678901", False, False),
    ("near-asia-word", "https://h.example/x/ASIAPACIFICREGION123", False, False),
    ("near-npm-config", "https://docs.npmjs.com/cli/npm_config_registry", False, False),
    ("near-pat-slug", "https://docs.github.com/github_pat_creation_page", False, False),
    (
        "near-glpat-slug",
        "https://docs.gitlab.com/glpat-token-rotation-guide-v2",
        False,
        False,
    ),
    (
        "near-xoxb-slug",
        "https://api.slack.com/xoxb-bot-token-scopes-explained",
        False,
        False,
    ),
    (
        "near-pypi-slug",
        "https://h.example/pypi-simple-index-mirror-configuration-for-enterprise-use",
        False,
        False,
    ),
    ("near-hf", "https://huggingface.co/docs/hf_hub_download", False, False),
    (
        "near-sha",
        "https://h.example/0123456789abcdef0123456789abcdef01234567",
        False,
        False,
    ),
    # Prose: a sentence is never refused, whatever it mentions.
    ("prose-url", f"see {_URL} for details", True, False),
    ("prose-readme", "Example: https://user:S3CRET@example.com/repo.git", True, False),
    ("prose-query", "get https://h.example/x?token=T0KEN, then run", True, False),
    ("prose-marks", f"see {marks(17)} ok", True, False),
    ("prose-quote", "see https://o'brien:S3CRET@h.example/x", False, False),
    ("prose-space", "see https://h/a b?token=T0KEN", False, False),
    ("prose-weak", "see https://h.example/x?code=abc ok", False, False),
    (
        "prose-port",
        "Open http://localhost:<port> in a browser; mail d@e.org",
        False,
        False,
    ),
    ("prose-mail", "Visit https://h.example and mail a@b.org", False, False),
    ("prose-req", "needs name @ https://h.example/x.whl?token=T0KEN, ok", True, False),
    ("prose-scp", "clone alice:S3CRET@host.example:o/r now", False, False),
    ("prose-build", "run build:42@ci:linux now", False, False),
    ("prose-aws", "Set AKIAIOSFODNN7EXAMPLE in the environment", False, False),
    ("prose-ghp", f"use ghp_{b62(36)} here", False, False),
    ("prose-hf-env", f"HF_TOKEN=hf_{_HF}", False, False),
    ("prose-slugs", "glpat-token-rotation-guide-v2 and hf_hub_download", False, False),
)
