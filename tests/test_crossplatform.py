"""Cross-platform stability tests (no network required)."""

import hashlib
from pathlib import Path

import numpy as np
import pytest

from tellmewords.audio import segment_usable_regions, all_samples_region
from tellmewords.config import TuningConfig, serialize, deserialize, VERSION
from tellmewords.codebook import CoordinateEntry


def test_segmentation_stability(synthetic_pcm):
    """segment_usable_regions is deterministic for the same array."""
    regions_a = segment_usable_regions(synthetic_pcm)
    regions_b = segment_usable_regions(synthetic_pcm)
    assert regions_a == regions_b


def test_segmentation_100_runs(synthetic_pcm):
    first = segment_usable_regions(synthetic_pcm)
    for _ in range(99):
        assert segment_usable_regions(synthetic_pcm) == first


def test_synthetic_wav_hash_deterministic(synthetic_wav_path):
    """The generated synthetic WAV has a stable SHA-256 across reads."""
    h1 = hashlib.sha256(synthetic_wav_path.read_bytes()).hexdigest()
    h2 = hashlib.sha256(synthetic_wav_path.read_bytes()).hexdigest()
    assert h1 == h2


def test_config_json_deterministic_with_seed():
    """Serialization is deterministic for the same rng_seed."""
    coords = [CoordinateEntry(position=i * 50, correction_mask=i % 256) for i in range(10)]
    cfg = TuningConfig(
        version=VERSION,
        youtube_url="https://www.youtube.com/watch?v=stable",
        audio_hash="c" * 64,
        hamming_tolerance=0,
        rs_nsym=5,
        coordinate_list=coords,
    )
    s1 = serialize(cfg, rng_seed=123)
    s2 = serialize(cfg, rng_seed=123)
    assert s1 == s2


def test_pcm_lsb_extraction_deterministic(synthetic_pcm):
    """Extracting LSBs twice from the same array yields the same result."""
    lsbs_a = (synthetic_pcm & 1).astype(np.uint8)
    lsbs_b = (synthetic_pcm & 1).astype(np.uint8)
    assert np.array_equal(lsbs_a, lsbs_b)
