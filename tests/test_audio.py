"""Tests for audio.py segmentation logic (offline)."""

import numpy as np
import pytest

from tellmewords.audio import segment_usable_regions, all_samples_region, _merge_regions


def _make_silence(n: int) -> np.ndarray:
    return np.zeros(n, dtype=np.int16)


def _make_voiced(n: int, amplitude: int = 8000) -> np.ndarray:
    t = np.arange(n)
    return (np.sin(2 * np.pi * 440 * t / 44100) * amplitude).astype(np.int16)


def test_all_silence_returns_empty():
    pcm = _make_silence(44100)
    regions = segment_usable_regions(pcm)
    assert regions == []


def test_all_voiced_returns_one_region(synthetic_pcm):
    # Synthetic audio has pseudo-random amplitude — should be detected as voiced
    regions = segment_usable_regions(synthetic_pcm)
    assert len(regions) >= 1


def test_all_samples_region_covers_everything(synthetic_pcm):
    regions = all_samples_region(synthetic_pcm)
    assert len(regions) == 1
    start, end = regions[0]
    assert start == 0
    assert end == len(synthetic_pcm)


def test_merge_regions_adjacent():
    regions = [(0, 1000), (1100, 2000)]  # gap of 100 < _MIN_GAP=4410
    merged = _merge_regions(regions, min_gap=4410)
    assert len(merged) == 1
    assert merged[0] == (0, 2000)


def test_merge_regions_far_apart():
    regions = [(0, 1000), (10000, 20000)]  # gap of 9000 > _MIN_GAP=4410
    merged = _merge_regions(regions, min_gap=4410)
    assert len(merged) == 2


def test_voiced_regions_exclude_silence():
    # 2s silence + 2s voiced + 2s silence
    silence = _make_silence(2 * 44100)
    voiced = _make_voiced(2 * 44100)
    pcm = np.concatenate([silence, voiced, silence])
    regions = segment_usable_regions(pcm)
    assert len(regions) >= 1
    # All regions should be in the voiced section (middle third)
    for start, end in regions:
        assert start >= 44100 * 1, f"Region starts too early: {start}"
        assert end <= 44100 * 5, f"Region ends too late: {end}"
