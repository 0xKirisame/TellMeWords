"""Encode pipeline: message + YouTube URL → TuningConfig (+ optional Gist upload)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tellmewords import audio, codebook, config, ec


def encode(
    youtube_url: str,
    message: str | bytes,
    hamming_tolerance: int = 0,
    redundancy: float = 0.30,
    gist_token: str | None = None,
    cache_dir: Path | None = None,
    use_all_samples: bool = False,
) -> tuple[config.TuningConfig, str | None]:
    """Encode a message against a YouTube audio file.

    Returns (TuningConfig, gist_url_or_None).
    If gist_token is provided, uploads the config and returns the Gist URL.
    """
    if isinstance(message, str):
        message_bytes = message.encode("utf-8")
    else:
        message_bytes = message

    # 1. Download and decode audio
    pcm, sha256 = audio.download(youtube_url, cache_dir=cache_dir)

    # 2. Segment usable regions
    if use_all_samples:
        regions = audio.all_samples_region(pcm)
    else:
        regions = audio.segment_usable_regions(pcm)

    if not regions:
        raise ValueError("No usable voiced regions found in audio. Try a different video.")

    # 3. Error-correct the message
    nsym = ec.default_nsym(len(message_bytes), redundancy)
    padded = ec.rs_encode(message_bytes, nsym)

    # 4. Build inverted index
    idx = codebook.build_inverted_index(pcm, regions, hamming_tolerance=hamming_tolerance)

    # 5. Derive coordinate list
    coordinates = codebook.encode_message(idx, pcm, padded)

    # 6. Assemble TuningConfig
    cfg = config.TuningConfig(
        version=config.VERSION,
        youtube_url=youtube_url,
        audio_hash=sha256,
        hamming_tolerance=hamming_tolerance,
        rs_nsym=nsym,
        coordinate_list=coordinates,
    )

    # 7. Optionally upload to Gist
    gist_url = None
    if gist_token:
        gist_url = config.upload_gist(cfg, gist_token)

    return cfg, gist_url
