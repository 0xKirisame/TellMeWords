"""Generate a deterministic 60-second synthetic WAV for offline tests.

Usage:
    python tests/fixtures/generate_synthetic_audio.py
Writes synthetic_60s.wav in the same directory.
"""

import io
import struct
import sys
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile

SEED = 42
SAMPLE_RATE = 44100
DURATION_S = 60
N_SAMPLES = SAMPLE_RATE * DURATION_S


def generate(seed: int = SEED) -> np.ndarray:
    """Return (N_SAMPLES, 2) int16 stereo PCM array from a fixed PRNG seed."""
    rng = np.random.default_rng(seed)
    # Pseudo-random int16 — ensures all 256 byte values appear in LSB stream
    samples = rng.integers(-32768, 32767, size=(N_SAMPLES, 2), dtype=np.int16)
    return samples


def write(path: Path, samples: np.ndarray) -> None:
    buf = io.BytesIO()
    wavfile.write(buf, SAMPLE_RATE, samples)
    path.write_bytes(buf.getvalue())


if __name__ == "__main__":
    out = Path(__file__).parent / "synthetic_60s.wav"
    print(f"Generating {out} …", flush=True)
    write(out, generate())
    print(f"Done. Size: {out.stat().st_size:,} bytes")
