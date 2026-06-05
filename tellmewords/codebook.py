"""Inverted-index codebook: build, encode, decode."""

from __future__ import annotations

import bisect
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class CoordinateEntry:
    position: int        # absolute sample index where the 8-LSB window starts
    correction_mask: int # XOR this with extracted byte to recover intended byte; 0 = exact match


class InsufficientCapacityError(Exception):
    pass


# ---------------------------------------------------------------------------
# Hamming distance helpers
# ---------------------------------------------------------------------------

def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _bytes_within_hamming(b: int, d: int) -> list[tuple[int, int]]:
    """Return (byte_value, correction_mask) for all values within Hamming distance d of b."""
    results = []
    for candidate in range(256):
        dist = _hamming_distance(b, candidate)
        if dist <= d:
            results.append((candidate, b ^ candidate))
    return results


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------

def build_inverted_index(
    pcm: "np.ndarray",  # shape (N,) dtype int16, left channel samples
    usable_regions: list[tuple[int, int]],
    hamming_tolerance: int = 0,
) -> dict[int, deque[int]]:
    """Build inverted index: byte_value -> deque of sample positions.

    Each position i means the 8 LSBs of pcm[i:i+8] form byte_value
    (possibly after XOR with correction_mask for hamming_tolerance > 0).

    The deque stores raw positions (no correction — correction is resolved at
    encode time by looking up the natural byte at each position).
    """
    import numpy as np

    index: dict[int, deque[int]] = {v: deque() for v in range(256)}

    for start, end in usable_regions:
        # We need at least 8 samples per window
        region_end = end - 7
        if region_end <= start:
            continue

        # Extract the LSB of each sample in this region
        region = pcm[start:end].astype(np.int16)
        lsbs = (region & 1).astype(np.uint8)

        # Slide an 8-bit window through the region
        for i in range(start, region_end):
            local = i - start
            # Pack 8 consecutive LSBs into one byte (MSB first)
            b_nat = int(
                (lsbs[local] << 7)
                | (lsbs[local + 1] << 6)
                | (lsbs[local + 2] << 5)
                | (lsbs[local + 3] << 4)
                | (lsbs[local + 4] << 3)
                | (lsbs[local + 5] << 2)
                | (lsbs[local + 6] << 1)
                | lsbs[local + 7]
            )

            if hamming_tolerance == 0:
                index[b_nat].append(i)
            else:
                for target, _mask in _bytes_within_hamming(b_nat, hamming_tolerance):
                    index[target].append(i)

    return index


def _extract_byte_at(pcm: "np.ndarray", position: int) -> int:
    """Extract the natural byte from 8 LSBs starting at position."""
    import numpy as np
    samples = pcm[position : position + 8].astype(np.int16)
    lsbs = (samples & 1).astype(np.uint8)
    return int(
        (lsbs[0] << 7) | (lsbs[1] << 6) | (lsbs[2] << 5) | (lsbs[3] << 4)
        | (lsbs[4] << 3) | (lsbs[5] << 2) | (lsbs[6] << 1) | lsbs[7]
    )


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------

def encode_message(
    index: dict[int, deque[int]],
    pcm: "np.ndarray",
    padded_payload: bytes,
) -> list[CoordinateEntry]:
    """Map each byte in padded_payload to a CoordinateEntry using the index.

    Guarantees no two assigned positions overlap within an 8-sample window.
    Raises InsufficientCapacityError if any byte value has no available positions.
    """
    used: list[int] = []  # sorted list of assigned positions, for bisect overlap checks
    coordinates: list[CoordinateEntry] = []

    for byte_val in padded_payload:
        q = index.get(byte_val)
        if q is None or len(q) == 0:
            raise InsufficientCapacityError(
                f"No positions available for byte value 0x{byte_val:02x}"
            )

        position = _pop_non_overlapping(q, used)
        if position is None:
            raise InsufficientCapacityError(
                f"Positions for byte 0x{byte_val:02x} all overlap with already-used positions"
            )

        b_nat = _extract_byte_at(pcm, position)
        correction_mask = b_nat ^ byte_val
        coordinates.append(CoordinateEntry(position=position, correction_mask=correction_mask))
        _insert_sorted(used, position)

    return coordinates


def _pop_non_overlapping(q: deque[int], used_sorted: list[int]) -> int | None:
    """Pop the first position from q that doesn't overlap (±7) with any used position."""
    attempts = []
    result = None

    while q:
        p = q.popleft()
        if _overlaps(p, used_sorted):
            attempts.append(p)
        else:
            result = p
            break

    # Return discarded positions to the front of the deque (in reverse order)
    for p in reversed(attempts):
        q.appendleft(p)

    return result


def _overlaps(position: int, used_sorted: list[int]) -> bool:
    """Return True if position is within 7 samples of any used position."""
    # Find insertion point; check neighbors
    idx = bisect.bisect_left(used_sorted, position - 7)
    while idx < len(used_sorted) and used_sorted[idx] <= position + 7:
        if abs(used_sorted[idx] - position) <= 7:
            return True
        idx += 1
    return False


def _insert_sorted(lst: list[int], value: int) -> None:
    bisect.insort(lst, value)


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------

def decode_coordinates(
    pcm: "np.ndarray",
    coordinates: list[CoordinateEntry],
) -> bytes:
    """Extract bytes from pcm at each coordinate position, applying correction masks."""
    result = bytearray()
    for entry in coordinates:
        b_nat = _extract_byte_at(pcm, entry.position)
        result.append(b_nat ^ entry.correction_mask)
    return bytes(result)
