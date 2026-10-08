# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The header and label strings of a CRFsuite model, nothing else.

A CRFsuite model (``lCRF``, first-order Markov CRF ``FOMC``, version 100)
is a 48-byte little-endian header and five chunks in a fixed order:
``FEAT`` (the feature weights), a ``CQDB`` string database of labels, a
``CQDB`` of attributes, ``LFRF`` and ``AFRF`` (feature references).
:func:`read_crfsuite` reads the header, the chunk headers, and the labels
database whole under :attr:`Limits.max_crfsuite_labels_chunk_bytes`. It never
reads the weights, the attribute strings (training-text features) or the
reference lists. A model over a labels bound is still read, without its
label strings: the counts and the type are known from the headers.

CRFsuite itself checks almost none of this; every bound here is the
reader's own. ``CQDB`` offsets are relative to the start of their chunk,
and a record's key length counts its trailing NUL.

See also: :mod:`pitloom.extract.ai_model.crfsuite` (Pitloom's adapter).
"""

from __future__ import annotations

import os
import struct
from typing import IO, NamedTuple

from ._errors import Malformed, UnsupportedVersion
from ._limits import Limits

_HEADER = struct.Struct("<4sI4sIIIIIIIII")
_CHUNK = struct.Struct("<4sII")  # FEAT, LFRF, AFRF: tag, size, num
_CQDB = struct.Struct("<4sIIIII")  # tag, size, flag, byteorder, bwd size/offset
_RECORD = struct.Struct("<iI")  # id, key size (NUL included)
_MAGIC = b"lCRF"
_TYPE = b"FOMC"
_VERSION = 100
_FEATURE_SIZE = 20
_CQDB_BYTEORDER = 0x62445371
_CQDB_TABLES = 256  # hash tables, each a (offset, num) ref of two u32
_CQDB_DATA_START = 24 + 8 * _CQDB_TABLES  # records start after the refs (2072)
_BUCKET_SIZE = 8  # a hash-table bucket: u32 hash, u32 record offset


class CrfsuiteModel(NamedTuple):
    """What a CRFsuite model file says about itself.

    Attributes:
        model_type: The header's model type (``"FOMC"``).
        version: The header's format version (100).
        num_features: The ``FEAT`` chunk's count; the header's own
            ``num_features`` is never set by CRFsuite.
        num_attributes: How many attribute strings the model holds.
        num_labels: How many labels the model holds.
        labels: The label strings, in id order (the training's first-seen
            order). Bytes before the first NUL, decoded as UTF-8 with
            ``backslashreplace``. ``None`` when a labels bound kept them
            unread.
        labels_unread: Why the labels were not read (the bound exceeded,
            one short phrase), or ``None`` when they were.
    """

    model_type: str
    version: int
    num_features: int
    num_attributes: int
    num_labels: int
    labels: tuple[str, ...] | None
    labels_unread: str | None = None


class _Header(NamedTuple):
    size: int
    num_labels: int
    num_attrs: int
    off_features: int
    off_labels: int
    off_attrs: int
    off_labelrefs: int
    off_attrrefs: int


class _Cqdb(NamedTuple):
    size: int
    bwd_size: int
    bwd_offset: int


def read_crfsuite(source: IO[bytes], limits: Limits) -> CrfsuiteModel:
    """Read a CRFsuite model's header and label strings, nothing else.

    *source* is a seekable binary file. Reads the 48-byte header, the
    ``FEAT``/``LFRF``/``AFRF`` chunk headers, the labels chunk (whole,
    bounded) and the attributes chunk header: at most
    ``limits.max_crfsuite_labels_chunk_bytes + 108`` bytes. Bytes past the
    header's ``size`` are ignored.

    More labels than :attr:`Limits.max_crfsuite_labels`, or a labels chunk
    over :attr:`Limits.max_crfsuite_labels_chunk_bytes`, leaves the labels
    chunk unread past its header: ``labels`` is ``None`` and
    ``labels_unread`` says which bound. Every other check still applies.

    Raises:
        Malformed: Truncated, a wrong magic or chunk tag, or sizes,
            offsets or records inconsistent with each other.
        UnsupportedVersion: A model type other than ``FOMC``, a version
            other than 100, or a labels chunk with an unknown byte order
            or flag.
    """
    header = _read_header(source)
    num_features = _read_feature_count(source, header)
    labels, unread = _read_labels(source, header, limits)
    _check_attributes(source, header)
    _check_references(source, header)
    return CrfsuiteModel(
        _TYPE.decode("ascii"),
        _VERSION,
        num_features,
        header.num_attrs,
        header.num_labels,
        labels,
        unread,
    )


def _read_exact(source: IO[bytes], offset: int, size: int) -> bytes:
    """Exactly *size* bytes at *offset*; a short read is truncation."""
    source.seek(offset)
    data = source.read(size)
    if len(data) != size:
        raise Malformed(f"truncated at offset {offset + len(data)}")
    return data


def _read_header(source: IO[bytes]) -> _Header:
    """Checks 1 to 5: the header and where the chunks are."""
    file_size = source.seek(0, os.SEEK_END)
    if file_size < _HEADER.size:
        raise Malformed("header truncated")
    (magic, size, model_type, version, _num_features, *rest) = _HEADER.unpack(
        _read_exact(source, 0, _HEADER.size)
    )
    if magic != _MAGIC:
        raise Malformed("magic is not lCRF")
    if model_type != _TYPE:
        raise UnsupportedVersion(f"model type {model_type!r} is not FOMC")
    if version != _VERSION:
        raise UnsupportedVersion(f"format version {version} is not 100")
    if not _HEADER.size <= size <= file_size:
        raise Malformed(f"declared size {size}, file is {file_size} bytes")
    header = _Header(size, *rest)
    _check_offsets(header)
    return header


def _check_offsets(header: _Header) -> None:
    """Check 5: the chunks in order, each chunk header inside ``size``."""
    offsets = (
        (header.off_features, _CHUNK.size),
        (header.off_labels, _CQDB.size),
        (header.off_attrs, _CQDB.size),
        (header.off_labelrefs, _CHUNK.size),
        (header.off_attrrefs, _CHUNK.size),
    )
    previous = _HEADER.size - 1
    for offset, chunk_header in offsets:
        if offset <= previous or offset + chunk_header > header.size:
            raise Malformed("chunk offsets out of order or outside the file")
        previous = offset


def _read_feature_count(source: IO[bytes], header: _Header) -> int:
    """Check 6: the ``FEAT`` chunk header; its count is the feature count."""
    tag, size, num = _CHUNK.unpack(
        _read_exact(source, header.off_features, _CHUNK.size)
    )
    if tag != b"FEAT":
        raise Malformed("FEAT chunk tag missing")
    if size != _CHUNK.size + _FEATURE_SIZE * num:
        raise Malformed("FEAT chunk size does not match its count")
    if header.off_features + size > header.off_labels:
        raise Malformed("FEAT chunk overlaps the labels chunk")
    return int(num)


def _read_labels(
    source: IO[bytes], header: _Header, limits: Limits
) -> tuple[tuple[str, ...] | None, str | None]:
    """Checks 8 to 11: the labels ``CQDB``, read whole once bounded.

    Returns ``(labels, None)``, or ``(None, reason)`` with the chunk's
    header checked but the chunk unread when a bound is exceeded.
    """
    raw = _read_exact(source, header.off_labels, _CQDB.size)
    tag, size, flag, byteorder, bwd_size, bwd_offset = _CQDB.unpack(raw)
    if tag != b"CQDB":
        raise Malformed("labels CQDB tag missing")
    if byteorder != _CQDB_BYTEORDER:
        raise UnsupportedVersion(f"labels CQDB byte order {byteorder:#010x}")
    if flag != 0:
        raise UnsupportedVersion(f"labels CQDB flag {flag}")
    if not _CQDB_DATA_START <= size <= header.off_attrs - header.off_labels:
        raise Malformed("labels CQDB size outside its chunk")
    cqdb = _Cqdb(size, bwd_size, bwd_offset)
    _check_backward_array(cqdb, header.num_labels, "labels")
    if header.num_labels > limits.max_crfsuite_labels:
        return None, f"more than {limits.max_crfsuite_labels} labels"
    if size > limits.max_crfsuite_labels_chunk_bytes:
        return None, f"labels CQDB over {limits.max_crfsuite_labels_chunk_bytes} bytes"
    chunk = raw + _read_exact(source, header.off_labels + _CQDB.size, size - _CQDB.size)
    _check_hash_tables(chunk, cqdb)
    labels = tuple(_decode_label(chunk, cqdb, i) for i in range(header.num_labels))
    return labels, None


def _check_backward_array(cqdb: _Cqdb, count: int, what: str) -> None:
    """Check 10 (and 12): one backward-array entry per item, inside the chunk."""
    if cqdb.bwd_size != count:
        raise Malformed(f"{what} CQDB count differs from the header")
    if count and not (
        _CQDB_DATA_START <= cqdb.bwd_offset and cqdb.bwd_offset + 4 * count <= cqdb.size
    ):
        raise Malformed(f"{what} backward array outside its chunk")


def _check_hash_tables(chunk: bytes, cqdb: _Cqdb) -> None:
    """Check 10: the hash-table refs of the labels ``CQDB``.

    CRFsuite sizes its backward array from the table counts (each table
    holds two buckets per record) and reads each table at its offset, so
    counts or offsets that disagree with the file make it read past its
    buffers. The reader never hashes, but refuses such a file.
    """
    refs = struct.unpack_from(f"<{2 * _CQDB_TABLES}I", chunk, _CQDB.size)
    if sum(num // 2 for num in refs[1::2]) != cqdb.bwd_size:
        raise Malformed("labels hash table counts differ from the label count")
    for offset, num in zip(refs[0::2], refs[1::2], strict=True):
        if offset and not (
            _CQDB_DATA_START <= offset and offset + _BUCKET_SIZE * num <= cqdb.size
        ):
            raise Malformed("labels hash table outside its chunk")


def _decode_label(chunk: bytes, cqdb: _Cqdb, label_id: int) -> str:
    """Check 11: label *label_id*'s record, found by the backward array."""
    (rec_off,) = struct.unpack_from("<I", chunk, cqdb.bwd_offset + 4 * label_id)
    if not _CQDB_DATA_START <= rec_off <= cqdb.size - _RECORD.size:
        raise Malformed(f"label {label_id} record outside its chunk")
    rec_id, ksize = _RECORD.unpack_from(chunk, rec_off)
    key_end = rec_off + _RECORD.size + ksize
    if rec_id != label_id or ksize < 1 or key_end > cqdb.size:
        raise Malformed(f"label {label_id} record is inconsistent")
    if chunk[key_end - 1] != 0:
        raise Malformed(f"label {label_id} is not NUL-terminated")
    key = chunk[rec_off + _RECORD.size : key_end - 1].split(b"\0", 1)[0]
    return key.decode("utf-8", errors="backslashreplace")


def _check_attributes(source: IO[bytes], header: _Header) -> None:
    """Check 12: the attributes ``CQDB`` header only, never its strings."""
    tag, size, _flag, byteorder, bwd_size, bwd_offset = _CQDB.unpack(
        _read_exact(source, header.off_attrs, _CQDB.size)
    )
    if tag != b"CQDB":
        raise Malformed("attributes CQDB tag missing")
    if byteorder != _CQDB_BYTEORDER:
        raise Malformed("attributes CQDB byte order differs from the labels'")
    if not _CQDB_DATA_START <= size <= header.off_labelrefs - header.off_attrs:
        raise Malformed("attributes CQDB size outside its chunk")
    _check_backward_array(
        _Cqdb(size, bwd_size, bwd_offset), header.num_attrs, "attributes"
    )
    # AFRF holds one u32 offset per attribute
    if header.off_attrrefs + _CHUNK.size + 4 * header.num_attrs > header.size:
        raise Malformed("attribute count does not fit in the file")


def _check_references(source: IO[bytes], header: _Header) -> None:
    """Check 13: the ``LFRF`` and ``AFRF`` chunk headers and counts.

    ``LFRF.num`` is ``num_labels + 2``: CRFsuite's writer opens the chunk
    with ``crf1dmw_open_labelrefs(writer, L+2)`` (``crf1d_encode.c``). It
    is only bounded, not compared: its offset array must fit before
    ``AFRF``.
    """
    tag, _size, num = _CHUNK.unpack(
        _read_exact(source, header.off_labelrefs, _CHUNK.size)
    )
    if tag != b"LFRF":
        raise Malformed("LFRF chunk tag missing")
    if header.off_labelrefs + _CHUNK.size + 4 * num > header.off_attrrefs:
        raise Malformed("LFRF count does not fit before AFRF")
    tag, _size, num = _CHUNK.unpack(
        _read_exact(source, header.off_attrrefs, _CHUNK.size)
    )
    if tag != b"AFRF":
        raise Malformed("AFRF chunk tag missing")
    if num != header.num_attrs:
        raise Malformed("AFRF count differs from the header")
