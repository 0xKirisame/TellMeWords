"""TuningConfig dataclass, UTAU-disguised JSON serialization, and GitHub Gist I/O."""

from __future__ import annotations

import json
import random
import string
from dataclasses import dataclass, asdict
from typing import Any

import requests

from tellmewords.codebook import CoordinateEntry


VERSION = "1.0"

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
# Serialization
# ---------------------------------------------------------------------------

def serialize(config: TuningConfig, rng_seed: int | None = None) -> str:
    """Serialize TuningConfig to a UTAU-disguised JSON string."""
    rng = random.Random(rng_seed)

    def _random_phoneme() -> str:
        return rng.choice(_PHONEMES)

    def _random_tone() -> str:
        return rng.choice(_TONES)

    def _random_volume() -> int:
        return rng.randint(85, 115)

    notes = []
    position_in_score = 480  # UTAU score position (ticks), advance per note

    for i, entry in enumerate(config.coordinate_list):
        # Split sample position into low 16 bits and high bits
        pbys = entry.position & 0xFFFF
        pbys_offset = entry.position >> 16

        note = {
            "position": position_in_score,
            "duration": rng.choice([240, 480, 720, 960]),
            "phoneme": _random_phoneme(),
            "tone": _random_tone(),
            "pbys": pbys,
            "pbys_offset": pbys_offset,
            "pby_mode": "curve",
            "velocity": entry.correction_mask,
            "volume": _random_volume(),
            "envelope": _DEFAULT_ENVELOPE[:],
        }
        notes.append(note)
        position_in_score += note["duration"]

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
        "tracks": [
            {
                "track_no": 0,
                "phoneme_sequence": " ".join(n["phoneme"] for n in notes),
                "notes": notes,
            }
        ],
        "_v": VERSION,
    }

    return json.dumps(doc, ensure_ascii=False, indent=2)


def deserialize(json_str: str) -> TuningConfig:
    """Parse a UTAU-disguised JSON string back into a TuningConfig."""
    doc = json.loads(json_str)

    youtube_url = doc["track_source"]["url"]
    audio_hash  = doc["track_source"]["checksum"]
    hamming     = doc["engine_params"]["tolerance_mode"]
    rs_nsym     = doc["engine_params"]["reverb_tail"]
    version     = doc.get("_v", "1.0")

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
