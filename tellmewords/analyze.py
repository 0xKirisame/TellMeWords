"""Usability analysis: score how well a video serves as a TellMeWords oracle."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np

from tellmewords import audio


_WINDOW_WEIGHTS = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint16)

# Typical fraction of spaces in natural-language ASCII text (~17%)
_ENGLISH_SPACE_FRACTION = 0.17


@dataclass
class UsabilityReport:
    youtube_url: str
    sha256: str
    duration_seconds: float
    total_samples: int
    usable_regions: int
    usable_samples: int
    coverage_pct: float
    windows: int
    lsb_entropy_bits: float
    rarest_byte: int
    rarest_byte_count: int
    median_byte_count: int
    most_common_byte_count: int
    worst_case_padded_bytes: int      # bounded by rarest byte value
    worst_case_plaintext_bytes: int   # after ~30% RS overhead
    english_estimate_bytes: int       # heuristic bound via space frequency
    worst_case_bytes_per_minute: float  # density: worst-case padded / minutes
    efficiency_pct: float             # vs theoretical max (44100*60/256 ≈ 10,336 B/min)
    verdict: str                      # EXCELLENT / GOOD / MARGINAL / POOR

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Theoretical ceiling: every sample usable, perfectly uniform byte distribution.
_THEORETICAL_BPM = 44100 * 60 / 256


def analyze(
    youtube_url: str,
    cache_dir: Path | None = None,
) -> UsabilityReport:
    """Download (or use cached) oracle audio and measure its steganographic capacity."""
    pcm, sha256 = audio.download(youtube_url, cache_dir=cache_dir)
    regions = audio.segment_usable_regions(pcm)

    total = len(pcm)
    usable = sum(end - start for start, end in regions)
    windows = sum(max(0, end - start - 7) for start, end in regions)

    # Byte-value histogram over all 8-LSB windows
    counts = np.zeros(256, dtype=np.int64)
    for start, end in regions:
        lsbs = (pcm[start:end] & 1).astype(np.uint8)
        n = len(lsbs) - 7
        if n <= 0:
            continue
        w = np.lib.stride_tricks.sliding_window_view(lsbs, 8)[:n]
        vals = w @ _WINDOW_WEIGHTS
        counts += np.bincount(vals, minlength=256)

    nonzero = counts[counts > 0]
    probs = nonzero / nonzero.sum()
    entropy = float(-(probs * np.log2(probs)).sum())

    rarest = int(counts.argmin())
    rarest_count = int(counts[rarest])
    median_count = int(np.median(nonzero)) if len(nonzero) else 0

    # English-text heuristic: capacity is bounded by whichever character is
    # scarcest relative to its expected frequency; spaces usually bind first.
    english_bound = (
        int(counts[0x20] / _ENGLISH_SPACE_FRACTION) if counts[0x20] > 0 else 0
    )

    minutes = total / 44100.0 / 60.0
    bpm_worst = rarest_count / minutes if minutes else 0.0
    efficiency = bpm_worst / _THEORETICAL_BPM * 100

    # Verdict is density-normalized so a 3-minute song competes fairly
    # against a 45-minute mix.
    if windows == 0 or entropy < 7.5:
        verdict = "POOR"
    elif efficiency >= 95:
        verdict = "EXCELLENT"
    elif efficiency >= 85:
        verdict = "GOOD"
    elif efficiency >= 60:
        verdict = "MARGINAL"
    else:
        verdict = "POOR"

    return UsabilityReport(
        youtube_url=youtube_url,
        sha256=sha256,
        duration_seconds=round(total / 44100.0, 1),
        total_samples=total,
        usable_regions=len(regions),
        usable_samples=usable,
        coverage_pct=round(usable / total * 100, 1) if total else 0.0,
        windows=windows,
        lsb_entropy_bits=round(entropy, 4),
        rarest_byte=rarest,
        rarest_byte_count=rarest_count,
        median_byte_count=median_count,
        most_common_byte_count=int(counts.max()),
        worst_case_padded_bytes=rarest_count,
        worst_case_plaintext_bytes=int(rarest_count / 1.3),
        english_estimate_bytes=english_bound,
        worst_case_bytes_per_minute=round(bpm_worst),
        efficiency_pct=round(efficiency, 1),
        verdict=verdict,
    )


def format_report(report: UsabilityReport) -> str:
    """Human-readable multi-line summary of a UsabilityReport."""
    r = report
    lines = [
        f"Oracle usability: {r.verdict}",
        f"  URL:            {r.youtube_url}",
        f"  Duration:       {r.duration_seconds}s ({r.total_samples:,} samples @ 44100 Hz)",
        f"  Usable regions: {r.usable_regions} covering {r.coverage_pct}% of audio",
        f"  8-bit windows:  {r.windows:,}",
        f"  LSB entropy:    {r.lsb_entropy_bits} bits (max 8.0)",
        f"  Byte counts:    rarest 0x{r.rarest_byte:02x} x{r.rarest_byte_count:,}, "
        f"median x{r.median_byte_count:,}, max x{r.most_common_byte_count:,}",
        "",
        "Estimated capacity:",
        f"  Worst-case payload (any byte pattern): ~{r.worst_case_padded_bytes:,} padded bytes "
        f"(~{r.worst_case_plaintext_bytes:,} plaintext after RS overhead)",
        f"  Natural English text (heuristic):      ~{r.english_estimate_bytes:,} bytes",
        "",
        f"Density: {r.worst_case_bytes_per_minute:,} worst-case B/min "
        f"({r.efficiency_pct}% of theoretical 10,336 B/min ceiling)",
    ]
    if r.verdict == "POOR":
        lines.append("")
        lines.append("Not recommended: too few stable, high-entropy positions. Try a louder, denser track.")
    return "\n".join(lines)
