"""Tests for config.py serialization and UTAU schema disguise."""

import json
import pytest

from tellmewords.codebook import CoordinateEntry
from tellmewords.config import TuningConfig, serialize, deserialize, VERSION


def _make_config(n_entries: int = 20) -> TuningConfig:
    coords = [CoordinateEntry(position=i * 100, correction_mask=i % 256) for i in range(n_entries)]
    return TuningConfig(
        version=VERSION,
        youtube_url="https://www.youtube.com/watch?v=abc123",
        audio_hash="a" * 64,
        hamming_tolerance=0,
        rs_nsym=10,
        coordinate_list=coords,
    )


def test_serialize_produces_valid_json():
    cfg = _make_config()
    json_str = serialize(cfg, rng_seed=0)
    doc = json.loads(json_str)
    assert isinstance(doc, dict)


def test_serialize_has_utau_fields():
    cfg = _make_config()
    doc = json.loads(serialize(cfg, rng_seed=0))
    assert "ustx_version" in doc
    assert "bpm" in doc
    assert "voice_bank" in doc
    assert "tracks" in doc
    assert len(doc["tracks"]) == 1
    assert "notes" in doc["tracks"][0]


def test_deserialize_roundtrip():
    cfg = _make_config(30)
    json_str = serialize(cfg, rng_seed=7)
    cfg2 = deserialize(json_str)

    assert cfg2.youtube_url == cfg.youtube_url
    assert cfg2.audio_hash == cfg.audio_hash
    assert cfg2.hamming_tolerance == cfg.hamming_tolerance
    assert cfg2.rs_nsym == cfg.rs_nsym
    assert len(cfg2.coordinate_list) == len(cfg.coordinate_list)

    for a, b in zip(cfg.coordinate_list, cfg2.coordinate_list):
        assert a.position == b.position, f"{a.position} != {b.position}"
        assert a.correction_mask == b.correction_mask


def test_large_position_survives_roundtrip():
    # Positions up to ~12M require pbys_offset > 0
    coords = [CoordinateEntry(position=12_000_000, correction_mask=255)]
    cfg = TuningConfig(
        version=VERSION,
        youtube_url="https://www.youtube.com/watch?v=test",
        audio_hash="b" * 64,
        hamming_tolerance=0,
        rs_nsym=4,
        coordinate_list=coords,
    )
    cfg2 = deserialize(serialize(cfg, rng_seed=1))
    assert cfg2.coordinate_list[0].position == 12_000_000
    assert cfg2.coordinate_list[0].correction_mask == 255


def test_note_count_matches_coordinate_list():
    cfg = _make_config(42)
    doc = json.loads(serialize(cfg, rng_seed=99))
    assert len(doc["tracks"][0]["notes"]) == 42


def test_youtube_url_preserved():
    cfg = _make_config()
    doc = json.loads(serialize(cfg))
    assert doc["track_source"]["url"] == cfg.youtube_url


def test_audio_hash_preserved():
    cfg = _make_config()
    doc = json.loads(serialize(cfg))
    assert doc["track_source"]["checksum"] == cfg.audio_hash
