"""BlackHat live demo script.

Usage:
    python demo/demo.py --url <youtube_url> [--message "text"] [--gist-token TOKEN]
    python demo/demo.py --offline   # uses pre-cached demo_config.json + synthetic audio
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

DEMO_DIR = Path(__file__).parent
REPO_ROOT = DEMO_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MESSAGE = "BlackHat2025 // 1A2b3C4d5E6f7G8h9I0j"
DEMO_CONFIG_PATH = DEMO_DIR / "demo_config.json"


def _banner() -> None:
    print(textwrap.dedent("""
    ╔══════════════════════════════════════════════════════════════╗
    ║         TellMeWords: Zero-Payload Steganography Demo           ║
    ║  Nothing is hidden. Nothing is modified. Yet here we are.   ║
    ╚══════════════════════════════════════════════════════════════╝
    """))


def _step(n: int, text: str) -> None:
    print(f"\n  [{n}] {text}")
    time.sleep(0.4)


def run_online(url: str, message: str, gist_token: str | None) -> None:
    from tellmewords import sender, receiver, config as cfg_mod
    from tellmewords.audio import all_samples_region

    _banner()

    _step(1, f"Oracle audio: {url}")
    print("      Downloading and decoding to 16-bit PCM … (this may take ~30s)")

    import tempfile
    cache = Path(tempfile.mkdtemp())
    tmw_config, gist_url = sender.encode(
        youtube_url=url,
        message=message,
        hamming_tolerance=0,
        cache_dir=cache,
        gist_token=gist_token,
    )

    json_str = cfg_mod.serialize(tmw_config, rng_seed=2025)

    _step(2, "Tuning config generated. Here's what the adversary sees:")
    print()
    # Show first 30 lines
    lines = json_str.splitlines()
    for line in lines[:30]:
        print("      " + line)
    if len(lines) > 30:
        print(f"      … ({len(lines) - 30} more lines, all looking like UTAU tuning data)")

    if gist_url:
        _step(3, f"Uploaded to GitHub Gist: {gist_url}")
    else:
        _step(3, "Config ready (no Gist token provided — would be posted to GitHub Gist)")

    _step(4, "Now decoding … (receiver downloads same audio, reads coordinate positions)")
    recovered = receiver.decode(tmw_config, cache_dir=cache, skip_hash_check=True)

    _step(5, "Recovered message:")
    print()
    print("      ┌─────────────────────────────────────────┐")
    print(f"      │  {recovered.decode('utf-8'):<41}│")
    print("      └─────────────────────────────────────────┘")

    _step(6, "What did we modify in the audio?")
    print()
    print("      Nothing. Zero bytes changed.")
    print(f"      The message was derived from {len(tmw_config.coordinate_list)} "
          f"positions already present in the audio.")
    print()


def run_offline() -> None:
    from tests.fixtures.generate_synthetic_audio import generate, SAMPLE_RATE
    from tellmewords import ec, codebook, config as cfg_mod
    from tellmewords.audio import all_samples_region

    _banner()

    _step(1, "Offline mode: using synthetic pseudo-random audio (no YouTube required)")

    if DEMO_CONFIG_PATH.exists():
        json_str = DEMO_CONFIG_PATH.read_text()
        _step(2, f"Loading pre-computed config from {DEMO_CONFIG_PATH}")
    else:
        print("      (No demo_config.json found — generating one now …)")
        pcm = generate()[:, 0]  # left channel
        msg = DEFAULT_MESSAGE.encode()
        nsym = ec.default_nsym(len(msg))
        padded = ec.rs_encode(msg, nsym)
        regions = all_samples_region(pcm)
        idx = codebook.build_inverted_index(pcm, regions)
        coords = codebook.encode_message(idx, pcm, padded)
        demo_cfg = cfg_mod.TuningConfig(
            version=cfg_mod.VERSION,
            youtube_url="https://www.youtube.com/watch?v=OFFLINE_DEMO",
            audio_hash="offline",
            hamming_tolerance=0,
            rs_nsym=nsym,
            coordinate_list=coords,
        )
        json_str = cfg_mod.serialize(demo_cfg, rng_seed=2025)
        DEMO_CONFIG_PATH.write_text(json_str)
        _step(2, f"Saved config to {DEMO_CONFIG_PATH}")

    doc = json.loads(json_str)
    lines = json_str.splitlines()
    _step(3, "Tuning config (adversary's view):")
    print()
    for line in lines[:25]:
        print("      " + line)
    if len(lines) > 25:
        print(f"      … ({len(lines) - 25} more lines)")

    _step(4, "Decoding from synthetic audio …")
    import numpy as np
    pcm = generate()[:, 0]
    cfg = cfg_mod.deserialize(json_str)
    if cfg.audio_hash == "offline":
        from tellmewords.ec import rs_decode
        raw = codebook.decode_coordinates(pcm, cfg.coordinate_list)
        recovered = rs_decode(raw, cfg.rs_nsym)
    else:
        from tellmewords.receiver import decode
        import tempfile
        recovered = decode(cfg, skip_hash_check=True)

    _step(5, "Recovered message:")
    print()
    print("      ┌─────────────────────────────────────────┐")
    print(f"      │  {recovered.decode('utf-8'):<41}│")
    print("      └─────────────────────────────────────────┘")

    _step(6, "What did we modify?")
    print()
    print("      Nothing. The message was always there — we just knew where to look.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="TellMeWords BlackHat Demo")
    parser.add_argument("--url", help="YouTube URL of oracle audio")
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--gist-token", help="GitHub token for Gist upload")
    parser.add_argument("--offline", action="store_true", help="Run without network")
    args = parser.parse_args()

    if args.offline:
        run_offline()
    elif args.url:
        run_online(args.url, args.message, args.gist_token)
    else:
        parser.print_help()
        print("\nTip: use --offline for a network-free demo.")


if __name__ == "__main__":
    main()
