"""Audio acquisition, deterministic PCM decode, and usable region segmentation."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile

# RMS thresholds (linear scale, not dB) for voiced-region detection
_RMS_HIGH = 10 ** (-30 / 20)   # enter voiced state above -30 dBFS
_RMS_LOW  = 10 ** (-45 / 20)   # leave voiced state below -45 dBFS

# Short-time RMS window and hop in samples
_RMS_WINDOW = 512
_RMS_HOP    = 256

# Minimum gap to merge (~0.1 s at 44100 Hz)
_MIN_GAP = 4410

# Trim from region boundaries to avoid transients (10 ms)
_BOUNDARY_TRIM = 441

# Common install locations for ffmpeg not always on PATH
_FFMPEG_SEARCH_PATHS = [
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
]


def _ffmpeg_bin() -> str:
    """Return the path to the ffmpeg binary, searching common locations."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for path in _FFMPEG_SEARCH_PATHS:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        "ffmpeg not found. Install it with: brew install ffmpeg"
    )


def download(youtube_url: str, cache_dir: Path | None = None) -> tuple[np.ndarray, str]:
    """Download a YouTube video and decode to left-channel 16-bit PCM at 44100 Hz.

    Returns (pcm_array, sha256_hex). Uses yt-dlp Python API and ffmpeg with
    integer PCM decode to guarantee bit-identical output across platforms.
    """
    work_dir = Path(cache_dir) if cache_dir else Path(tempfile.mkdtemp())
    work_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.md5(youtube_url.encode()).hexdigest()[:12]
    wav_path = work_dir / f"{url_hash}.wav"

    if not wav_path.exists():
        audio_path = _ytdlp_download(youtube_url, work_dir, url_hash)
        _ffmpeg_decode(audio_path, wav_path)

    wav_bytes = wav_path.read_bytes()
    sha256 = hashlib.sha256(wav_bytes).hexdigest()
    return _wav_to_pcm(wav_bytes), sha256


def _ytdlp_download(youtube_url: str, work_dir: Path, url_hash: str) -> Path:
    """Download audio using yt-dlp Python API. Returns path to downloaded file."""
    import yt_dlp

    out_template = str(work_dir / f"{url_hash}.audio.%(ext)s")
    ydl_opts = {
        "format": "bestaudio[format_id=251]/bestaudio[format_id=140]/bestaudio",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    candidates = list(work_dir.glob(f"{url_hash}.audio.*"))
    if not candidates:
        raise FileNotFoundError(f"yt-dlp produced no output for {youtube_url}")
    return candidates[0]


def _ffmpeg_decode(input_path: Path, wav_path: Path) -> None:
    """Decode audio to 16-bit stereo WAV at 44100 Hz using ffmpeg."""
    ffmpeg = _ffmpeg_bin()
    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "-f", "wav",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg decode failed:\n{result.stderr.decode(errors='replace')}"
        )


def load_wav(wav_path: Path) -> tuple[np.ndarray, str]:
    """Load a local WAV file. Returns (pcm_array, sha256_hex)."""
    wav_bytes = Path(wav_path).read_bytes()
    sha256 = hashlib.sha256(wav_bytes).hexdigest()
    return _wav_to_pcm(wav_bytes), sha256


def _wav_to_pcm(wav_bytes: bytes) -> np.ndarray:
    _, data = wavfile.read(io.BytesIO(wav_bytes))
    if data.ndim == 2:
        data = data[:, 0]  # left channel only
    return data.astype(np.int16)


def segment_usable_regions(
    pcm: np.ndarray,
    rms_high: float = _RMS_HIGH,
    rms_low: float = _RMS_LOW,
) -> list[tuple[int, int]]:
    """Return (start, end) sample pairs for voiced/mid-energy regions.

    Hysteresis thresholds: enter when RMS > rms_high, exit when RMS < rms_low.
    Adjacent regions within _MIN_GAP samples are merged; boundaries are trimmed
    by _BOUNDARY_TRIM samples to avoid transient artifacts.
    """
    n = len(pcm)
    pcm_f = pcm.astype(np.float32) / 32768.0

    num_frames = (n - _RMS_WINDOW) // _RMS_HOP + 1
    rms_frames = np.array([
        np.sqrt(np.mean(pcm_f[i * _RMS_HOP : i * _RMS_HOP + _RMS_WINDOW] ** 2))
        for i in range(num_frames)
    ])

    regions: list[tuple[int, int]] = []
    in_voiced = False
    region_start = 0

    for i, rms in enumerate(rms_frames):
        sample = i * _RMS_HOP
        if not in_voiced and rms > rms_high:
            region_start = sample
            in_voiced = True
        elif in_voiced and rms < rms_low:
            regions.append((region_start, sample + _RMS_WINDOW))
            in_voiced = False

    if in_voiced:
        regions.append((region_start, n))

    regions = _merge_regions(regions, _MIN_GAP)

    trimmed = []
    for start, end in regions:
        s = start + _BOUNDARY_TRIM
        e = end - _BOUNDARY_TRIM
        if e - s >= 16:
            trimmed.append((s, e))

    return trimmed


def all_samples_region(pcm: np.ndarray) -> list[tuple[int, int]]:
    """Single region covering all samples. Used for synthetic audio in tests."""
    return [(0, len(pcm))]


def _merge_regions(regions: list[tuple[int, int]], min_gap: int) -> list[tuple[int, int]]:
    if not regions:
        return []
    merged = [regions[0]]
    for start, end in regions[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end < min_gap:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged
