"""Shared pytest fixtures."""

import io
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile as wavfile

from tests.fixtures.generate_synthetic_audio import generate, SAMPLE_RATE

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SYNTHETIC_WAV = FIXTURE_DIR / "synthetic_60s.wav"


@pytest.fixture(scope="session")
def synthetic_pcm() -> np.ndarray:
    """Return left-channel int16 PCM from the synthetic 60-second WAV.

    Generates the file if it doesn't exist.
    """
    if not SYNTHETIC_WAV.exists():
        from tests.fixtures.generate_synthetic_audio import write
        write(SYNTHETIC_WAV, generate())

    _, data = wavfile.read(SYNTHETIC_WAV)
    if data.ndim == 2:
        return data[:, 0].astype(np.int16)
    return data.astype(np.int16)


@pytest.fixture(scope="session")
def synthetic_wav_path() -> Path:
    if not SYNTHETIC_WAV.exists():
        from tests.fixtures.generate_synthetic_audio import write
        write(SYNTHETIC_WAV, generate())
    return SYNTHETIC_WAV
