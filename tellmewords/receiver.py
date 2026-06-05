"""Decode pipeline: TuningConfig (or Gist URL) + YouTube audio → plaintext."""

from __future__ import annotations

from pathlib import Path

from tellmewords import audio, codebook, config, ec


def decode(
    cfg: config.TuningConfig,
    cache_dir: Path | None = None,
    skip_hash_check: bool = False,
    use_all_samples: bool = False,
) -> bytes:
    """Decode a message from a TuningConfig.

    Downloads the YouTube audio, verifies its SHA-256, extracts bytes at
    the coordinate positions, and RS-decodes to recover the original message.

    Raises ValueError if the audio hash doesn't match (indicates audio drift).
    """
    # 1. Download and decode audio
    pcm, sha256 = audio.download(cfg.youtube_url, cache_dir=cache_dir)

    # 2. Verify audio integrity
    if not skip_hash_check and sha256 != cfg.audio_hash:
        raise ValueError(
            f"Audio SHA-256 mismatch.\n"
            f"  Expected: {cfg.audio_hash}\n"
            f"  Got:      {sha256}\n"
            "The audio has changed since the config was created. "
            "Ensure you're using the same yt-dlp format and version."
        )

    # 3. Reconstruct raw bytes from coordinates
    raw_bytes = codebook.decode_coordinates(pcm, cfg.coordinate_list)

    # 4. RS decode
    return ec.rs_decode(raw_bytes, cfg.rs_nsym)


def decode_from_gist(
    gist_url: str,
    cache_dir: Path | None = None,
    skip_hash_check: bool = False,
) -> bytes:
    """Fetch TuningConfig from a Gist URL and decode the message."""
    cfg = config.fetch_gist(gist_url)
    return decode(cfg, cache_dir=cache_dir, skip_hash_check=skip_hash_check)


def decode_from_json(
    json_str: str,
    cache_dir: Path | None = None,
    skip_hash_check: bool = False,
) -> bytes:
    """Deserialize a TuningConfig JSON string and decode the message."""
    cfg = config.deserialize(json_str)
    return decode(cfg, cache_dir=cache_dir, skip_hash_check=skip_hash_check)
