"""End-to-end encode → decode round-trip tests (offline, synthetic audio)."""

import pytest
import numpy as np

from tellmewords import ec, codebook
from tellmewords.audio import all_samples_region
from tellmewords.config import serialize, deserialize, TuningConfig


def _roundtrip(pcm: np.ndarray, message: bytes, hamming: int = 0) -> bytes:
    """Encode message against pcm, then decode; returns recovered plaintext."""
    regions = all_samples_region(pcm)
    nsym = ec.default_nsym(len(message))
    padded = ec.rs_encode(message, nsym)
    idx = codebook.build_inverted_index(pcm, regions, hamming_tolerance=hamming)
    coords = codebook.encode_message(idx, pcm, padded)
    raw = codebook.decode_coordinates(pcm, coords)
    return ec.rs_decode(raw, nsym)


def test_roundtrip_short(synthetic_pcm):
    msg = b"correcthorsebatt"  # 16 bytes
    assert _roundtrip(synthetic_pcm, msg) == msg


def test_roundtrip_unicode(synthetic_pcm):
    msg = "こんにちは世界 — Steganiku demo".encode("utf-8")
    assert _roundtrip(synthetic_pcm, msg) == msg


def test_roundtrip_binary_all_bytes(synthetic_pcm):
    msg = bytes(range(256))
    assert _roundtrip(synthetic_pcm, msg) == msg


def test_roundtrip_hamming1(synthetic_pcm):
    msg = b"hamming tolerance test 1234!!"
    result = _roundtrip(synthetic_pcm, msg, hamming=1)
    assert result == msg


def test_roundtrip_hamming2(synthetic_pcm):
    msg = b"hamming distance 2 test!!!!!"
    result = _roundtrip(synthetic_pcm, msg, hamming=2)
    assert result == msg


def test_roundtrip_large(synthetic_pcm):
    msg = b"A" * 5000  # well within synthetic 60s capacity
    assert _roundtrip(synthetic_pcm, msg) == msg


def test_config_serialization_roundtrip(synthetic_pcm):
    """Serialize TuningConfig to JSON and back; verify fields survive the round-trip."""
    msg = b"serialization test"
    regions = all_samples_region(synthetic_pcm)
    nsym = ec.default_nsym(len(msg))
    padded = ec.rs_encode(msg, nsym)
    idx = codebook.build_inverted_index(synthetic_pcm, regions)
    coords = codebook.encode_message(idx, synthetic_pcm, padded)

    cfg = TuningConfig(
        version="1.0",
        youtube_url="https://www.youtube.com/watch?v=test123",
        audio_hash="deadbeef" * 8,
        hamming_tolerance=0,
        rs_nsym=nsym,
        coordinate_list=coords,
    )

    json_str = serialize(cfg, rng_seed=42)
    cfg2 = deserialize(json_str)

    assert cfg2.youtube_url == cfg.youtube_url
    assert cfg2.audio_hash == cfg.audio_hash
    assert cfg2.hamming_tolerance == cfg.hamming_tolerance
    assert cfg2.rs_nsym == cfg.rs_nsym
    assert len(cfg2.coordinate_list) == len(cfg.coordinate_list)
    for a, b in zip(cfg.coordinate_list, cfg2.coordinate_list):
        assert a.position == b.position
        assert a.correction_mask == b.correction_mask
