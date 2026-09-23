"""TuningConfig dataclass, UTAU-disguised JSON serialization, and GitHub Gist I/O."""

from __future__ import annotations

import base64
import json
import random
import string
import zlib
from dataclasses import dataclass
from typing import Any

import requests

from tellmewords.codebook import CoordinateEntry


VERSION = "1.1"

# UTAU note envelope shape (realistic default)
_DEFAULT_ENVELOPE = [0, 5, 35, 0, 100, 100, 0]

# Phoneme inventory used to populate fake note labels
_PHONEMES = ["a", "i", "u", "e", "o", "k", "s", "t", "n", "h", "m", "r", "w", "y",
             "ky", "sh", "ch", "ts", "ny", "hy", "my", "ry", "gy", "zy", "by", "py",
             "g", "z", "d", "b", "p", "f", "v", "ng", "sp", "cl"]

_TONES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5", "D5", "E5", "F5", "G5"]

_VOICE_BANKS = [
    "Kasane_Teto_v1.4",
    "IA_English_v2.0",
    "Momo_Momone_v3.1",
    "Defoko_v2.0",
    "Ritsu_Namine_v1.2",
]


@dataclass
class TuningConfig:
    version: str
    youtube_url: str
    audio_hash: str        # SHA-256 of the expected decoded WAV
    hamming_tolerance: int # 0 | 1 | 2
    rs_nsym: int
    coordinate_list: list[CoordinateEntry]


# ---------------------------------------------------------------------------
# Coordinate packing (binary, compressed)
# ---------------------------------------------------------------------------

def _put_varint(buf: bytearray, value: int) -> None:
    """Append an unsigned LEB128 varint."""
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            return


def _get_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read an unsigned LEB128 varint. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        b = data[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, offset
        shift += 7


def pack_coordinates(coordinates: list[CoordinateEntry]) -> str:
    """Pack coordinates into a compact base64 string.

    Layout per entry (payload order): zigzag-varint(position delta from the
    previous entry) + 1 raw correction-mask byte. The stream is then
    zlib-compressed and base64-encoded — roughly 10-15x smaller than one JSON
    object per note.
    """
    buf = bytearray()
    prev_pos = 0
    for entry in coordinates:
        delta = entry.position - prev_pos
        _put_varint(buf, (delta << 1) ^ (delta >> 63))  # zigzag
        buf.append(entry.correction_mask & 0xFF)
        prev_pos = entry.position
    return base64.b64encode(zlib.compress(bytes(buf), 9)).decode("ascii")


def unpack_coordinates(packed: str) -> list[CoordinateEntry]:
    """Inverse of pack_coordinates."""
    data = zlib.decompress(base64.b64decode(packed))
    coordinates: list[CoordinateEntry] = []
    offset = 0
    position = 0
    while offset < len(data):
        zz, offset = _get_varint(data, offset)
        delta = (zz >> 1) ^ -(zz & 1)
        position += delta
        mask = data[offset]
        offset += 1
        coordinates.append(CoordinateEntry(position=position, correction_mask=mask))
    return coordinates


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize(config: TuningConfig, rng_seed: int | None = None) -> str:
    """Serialize TuningConfig to a UTAU-disguised JSON string."""
    rng = random.Random(rng_seed)

    doc: dict[str, Any] = {
        "ustx_version": "0.6",
        "name": _make_project_name(config.youtube_url, rng),
        "comment": "Pitch correction and envelope tuning for performance render",
        "bpm": round(rng.uniform(118.0, 142.0), 1),
        "beat_per_bar": 4,
        "beat_unit": 4,
        "resolution": 480,
        "track_source": {
            "url": config.youtube_url,
            "checksum": config.audio_hash,
            "format": "wav/pcm_s16le/44100/stereo",
        },
        "engine_params": {
            "tolerance_mode": config.hamming_tolerance,
            "reverb_tail": config.rs_nsym,
            "render_engine": "worldline-r",
            "pitch_mode": "rapped",
        },
        "voice_bank": rng.choice(_VOICE_BANKS),
        # Compressed pitch-bend sample stream: zigzag-varint deltas + mask bytes
        "pbys_stream": pack_coordinates(config.coordinate_list),
        "_v": VERSION,
    }

    return json.dumps(doc, ensure_ascii=False)


def deserialize(json_str: str) -> TuningConfig:
    """Parse a UTAU-disguised JSON string back into a TuningConfig.

    Supports both the compressed stream format (v1.1+) and the legacy
    per-note JSON format (v1.0).
    """
    doc = json.loads(json_str)

    youtube_url = doc["track_source"]["url"]
    audio_hash  = doc["track_source"]["checksum"]
    hamming     = doc["engine_params"]["tolerance_mode"]
    rs_nsym     = doc["engine_params"]["reverb_tail"]
    version     = doc.get("_v", "1.0")

    if "pbys_stream" in doc:
        coordinates = unpack_coordinates(doc["pbys_stream"])
    else:
        coordinates = []
        for note in doc["tracks"][0]["notes"]:
            position = note["pbys"] | (note["pbys_offset"] << 16)
            correction_mask = note["velocity"]
            coordinates.append(CoordinateEntry(position=position, correction_mask=correction_mask))

    return TuningConfig(
        version=version,
        youtube_url=youtube_url,
        audio_hash=audio_hash,
        hamming_tolerance=hamming,
        rs_nsym=rs_nsym,
        coordinate_list=coordinates,
    )


def _make_project_name(url: str, rng: random.Random) -> str:
    """Derive a plausible UTAU project name from the YouTube URL."""
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=4))
    prefixes = ["aria", "melt", "packaged", "ghost", "comet", "planet", "star", "echo"]
    return f"{'_'.join(rng.choices(prefixes, k=2))}_tuning_{suffix}"


# ---------------------------------------------------------------------------
# GitHub Gist I/O
# ---------------------------------------------------------------------------

GIST_API = "https://api.github.com/gists"


def upload_gist(
    config: TuningConfig,
    token: str,
    filename: str | None = None,
    rng_seed: int | None = None,
) -> str:
    """Serialize config and upload as a public GitHub Gist. Returns the Gist URL."""
    if filename is None:
        filename = _make_project_name(config.youtube_url, random.Random(rng_seed)) + ".json"

    payload = {
        "description": "UTAU pitch correction tuning export",
        "public": True,
        "files": {
            filename: {
                "content": serialize(config, rng_seed=rng_seed),
            }
        },
    }
    resp = requests.post(
        GIST_API,
        json=payload,
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]


def fetch_gist(gist_url: str) -> TuningConfig:
    """Fetch a Gist by URL and deserialize its first file as a TuningConfig."""
    gist_id = gist_url.rstrip("/").split("/")[-1]
    resp = requests.get(
        f"{GIST_API}/{gist_id}",
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    first_file = next(iter(data["files"].values()))
    return deserialize(first_file["content"])
