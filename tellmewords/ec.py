"""Reed-Solomon encode/decode wrapper over reedsolo."""

from __future__ import annotations

import reedsolo


class RSDecodeError(Exception):
    pass


def rs_encode(data: bytes, nsym: int) -> bytes:
    """Return data + nsym RS parity bytes."""
    rs = reedsolo.RSCodec(nsym)
    return bytes(rs.encode(data))


def rs_decode(data: bytes, nsym: int) -> bytes:
    """Decode and return original data, correcting up to floor(nsym/2) byte errors.

    Raises RSDecodeError if the error count exceeds correction capacity.
    """
    rs = reedsolo.RSCodec(nsym)
    try:
        decoded, _, _ = rs.decode(data)
        return bytes(decoded)
    except reedsolo.ReedSolomonError as exc:
        raise RSDecodeError(str(exc)) from exc


def default_nsym(payload_len: int, redundancy: float = 0.30) -> int:
    """Return RS parity symbol count for a given payload length and redundancy ratio.

    reedsolo requires nsym < nsize (default nsize=255), so we cap at 64.
    nsym=64 gives 191 data bytes per chunk and can correct up to 32 byte errors per chunk.
    """
    nsym = max(4, int(payload_len * redundancy))
    return min(nsym, 64)
