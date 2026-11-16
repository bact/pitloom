# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An identifier minted from a name (``iri_segment`` percent-encodes it) is
read at each decode depth, each depth as a reader reads it; the masker
hides at every depth what the detector refuses, so a line never shows a
secret once decoded, however deep.

See also: _probe_corpus.py (the corpus), test_url_masking_detect.py (the
detector) and test_url_masking_mask.py (the masker) in this folder.
"""

from __future__ import annotations

from urllib.parse import unquote

import pytest

from pitloom.core.iri import iri_segment
from pitloom.core.url_masking import find_url_credentials, masked_given_path
from pitloom.core.url_masking._hits import PURL_DECODE_ROUNDS
from tests.core.url_masking._probe_corpus import PLANTED, PROBES, encoded

#: Values whose credential a decode shows, then a deeper one breaks or a
#: format character hides: each planted secret is ``S3CRET`` or ``T0KEN``.
_NEW = (
    ("slash-twice", "https:%2F%2Fu:S3%252FCRET@h"),
    # The deepest depth masks the token, shows the password the one before
    # it masked.
    ("slash-deeper-token", "https:%2F%2Fu:S3%252FCRET@h%2Fx%3Ftoken%3DT0KEN"),
    ("slash-minted", "https://u:S3CRET%2Fx@h/m"),
    ("zwsp-scheme", "https\u200b://u:S3CRET@h/m"),
    ("zwsp-slashes", "https:/\u200b/u:S3CRET@h"),
    ("word-joiner", "https://u:S3CRET\u2060@h"),
    ("soft-hyphen", "h\u00adttps://u:S3CRET@h"),
    ("bom", "\ufeffhttps://u:S3CRET@h"),
    ("line-feed", "htt\nps://u:S3CRET@h"),
    ("carriage-return", "htt\rps://u:S3CRET@h"),
    ("c0", "\x01https://u:S3CRET@h"),
    ("query", "hf://d/o?token=T0KEN"),
)
_REFUSED = tuple((row[0], row[1]) for row in PROBES if row[3]) + _NEW


def _depths(text: str) -> list[str]:
    """*text* and each percent-decode of it, to the end or one past the
    detector's rounds."""
    found = [text]
    for _ in range(PURL_DECODE_ROUNDS + 1):
        plain = unquote(found[-1])
        if plain == found[-1]:
            break
        found.append(plain)
    return found


def _ids(text: str) -> list[str]:
    """Identifiers built from *text*: as ``iri_segment`` mints one, and
    percent-encoded once and twice."""
    return [
        f"https://spdx.org/spdxdocs/{iri_segment(text)}-x#P",
        f"urn:x:{encoded(text, 1)}",
        f"urn:x:{encoded(text, 2)}",
    ]


def _shows_a_secret(text: str) -> bool:
    """Whether a decode depth of *text* shows a planted secret, a ``/`` a
    decode put in it (``S3%2FCRET``) not hiding it."""
    return any(
        secret in level.replace("/", "")
        for level in _depths(text)
        for secret in PLANTED
    )


#: Probes with white space in the URL: in a message *line* the masker ends
#: an unquoted URL at white space (its documented gap), so they are checked
#: as values only, as a line's value is masked before it is written.
_SPACED = frozenset({"ui-space", "q-space-path"})
#: Probes an id is not read for: an scp-style address is read as a whole
#: value only (a documented gap in an id).
_URLS = tuple(row for row in _REFUSED if "scp" not in row[0])


def _refused(value: str, *, embedded: bool) -> bool:
    found = find_url_credentials(value, embedded=embedded)
    return any(not f.weak for f in found)


@pytest.mark.parametrize(("probe", "text"), _REFUSED, ids=[row[0] for row in _REFUSED])
def test_what_the_detector_refuses_the_masker_hides_at_every_depth(
    probe: str, text: str
) -> None:
    """Differential, at each decode depth: a value the detector refuses,
    as written or in an id minted from it, masked shows no secret once
    decoded, however deep."""
    lines = (False,) if probe in _SPACED else (False, True)
    forms = ((text, False), *((value, True) for value in _ids(text)))
    for value, embedded in forms:
        if _refused(value, embedded=embedded):
            for line in lines:
                assert not _shows_a_secret(masked_given_path(value, line=line))


@pytest.mark.parametrize(("probe", "text"), _URLS, ids=[row[0] for row in _URLS])
def test_the_detector_refuses_an_id_minted_from_a_refused_url(
    probe: str, text: str
) -> None:
    """What the detector refuses as a URL or a token it refuses in an id
    minted from it, at each depth as a reader reads it, and no finding
    shows a secret at any depth. A token whose alphabet holds ``-`` glued
    to the id's own ``-x`` is a longer word: a documented gap."""
    forms = _ids(text)[1:] if probe.startswith("tok-") else _ids(text)
    for value in forms:
        found = find_url_credentials(value, embedded=True)
        assert any(not f.weak for f in found), value
        assert not any(_shows_a_secret(f.shown) for f in found)


@pytest.mark.parametrize(
    "name",
    ["ssh://git@github.com/org/m", "git+ssh://git@github.com/org/m.git"],
    ids=["ssh", "git+ssh"],
)
def test_an_id_minted_from_an_ssh_account_name_is_weak_only(name: str) -> None:
    """As in a URL field (``account``, the SBOM check's id reading):
    ``git@`` alone reaches the server, at each depth, and glued after an
    id's own text (``#AIPackage-ssh://git@h``); a password or a token with
    it is refused."""
    for value in (*_ids(name), f"urn:x:#AIPackage-{name}"):
        found = find_url_credentials(value, account=True, embedded=True)
        assert found and all(f.weak for f in found), value
    for secret in ("git:S3CRET@", f"ghp_{'aB3' * 12}@"):
        for value in _ids(name.replace("git@", secret)):
            found = find_url_credentials(value, account=True, embedded=True)
            assert any(not f.weak for f in found), value
