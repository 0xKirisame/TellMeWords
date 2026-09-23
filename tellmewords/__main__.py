"""CLI entry point: steganiku encode / decode / verify / index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tellmewords import analyze as analyze_mod
from tellmewords import audio, config, sender, receiver


def _cmd_encode(args: argparse.Namespace) -> None:
    message = args.message or sys.stdin.read()
    cfg, gist_url = sender.encode(
        youtube_url=args.url,
        message=message,
        hamming_tolerance=args.hamming,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        gist_token=args.gist_token,
    )

    if gist_url:
        print(f"Gist URL: {gist_url}", file=sys.stderr)
    else:
        json_str = config.serialize(cfg)
        if args.output:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"Config written to {args.output}", file=sys.stderr)
        else:
            print(json_str)


def _cmd_decode(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir) if args.cache_dir else None

    if args.gist:
        plaintext = receiver.decode_from_gist(
            args.gist,
            cache_dir=cache,
            skip_hash_check=args.skip_hash_check,
        )
    elif args.config_file:
        json_str = Path(args.config_file).read_text(encoding="utf-8")
        plaintext = receiver.decode_from_json(
            json_str,
            cache_dir=cache,
            skip_hash_check=args.skip_hash_check,
        )
    else:
        json_str = sys.stdin.read()
        plaintext = receiver.decode_from_json(
            json_str,
            cache_dir=cache,
            skip_hash_check=args.skip_hash_check,
        )

    if args.output_file:
        Path(args.output_file).write_bytes(plaintext)
    else:
        try:
            print(plaintext.decode("utf-8"))
        except UnicodeDecodeError:
            sys.stdout.buffer.write(plaintext)


def _cmd_verify(args: argparse.Namespace) -> None:
    """Download audio and verify its SHA-256 matches the config."""
    if args.gist:
        cfg = config.fetch_gist(args.gist)
    else:
        cfg = config.deserialize(Path(args.config_file).read_text(encoding="utf-8"))

    _, sha256 = audio.download(args.url or cfg.youtube_url, cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    match = sha256 == cfg.audio_hash
    status = "OK" if match else "MISMATCH"
    print(f"Audio hash check: {status}", file=sys.stderr)
    print(f"  Config:    {cfg.audio_hash}", file=sys.stderr)
    print(f"  Computed:  {sha256}", file=sys.stderr)
    if not match:
        sys.exit(1)


def _cmd_index(args: argparse.Namespace) -> None:
    """Pre-download and cache audio for faster encode/decode."""
    cache = Path(args.cache_dir) if args.cache_dir else Path(".tellmewords_cache")
    _, sha256 = audio.download(args.url, cache_dir=cache)
    print(f"Cached. SHA-256: {sha256}", file=sys.stderr)


def _cmd_analyze(args: argparse.Namespace) -> None:
    """Score how usable a video is as a TellMeWords oracle."""
    report = analyze_mod.analyze(
        args.url,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(analyze_mod.format_report(report))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tellmewords",
        description="Zero-payload steganography via opportunistic codebook derivation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # encode
    enc = sub.add_parser("encode", help="Encode a message into a tuning config")
    enc.add_argument("--url", required=True, help="YouTube URL of the oracle audio")
    enc.add_argument("--message", help="Plaintext message (reads stdin if omitted)")
    enc.add_argument("--hamming", type=int, default=0, choices=[0, 1, 2])
    enc.add_argument("--gist-token", help="GitHub personal access token for Gist upload")
    enc.add_argument("--output", "-o", help="Write config JSON to this file instead of stdout")
    enc.add_argument("--cache-dir", help="Directory for cached audio files")

    # decode
    dec = sub.add_parser("decode", help="Decode a message from a tuning config")
    src = dec.add_mutually_exclusive_group()
    src.add_argument("--gist", help="GitHub Gist URL")
    src.add_argument("--config-file", help="Local config JSON file")
    dec.add_argument("--output-file", help="Write decoded bytes to file instead of stdout")
    dec.add_argument("--cache-dir", help="Directory for cached audio files")
    dec.add_argument("--skip-hash-check", action="store_true")

    # verify
    ver = sub.add_parser("verify", help="Verify audio hash matches config")
    ver.add_argument("--url", help="Override YouTube URL")
    vsrc = ver.add_mutually_exclusive_group()
    vsrc.add_argument("--gist", help="GitHub Gist URL")
    vsrc.add_argument("--config-file")
    ver.add_argument("--cache-dir")

    # index
    idx = sub.add_parser("index", help="Pre-cache audio for a YouTube URL")
    idx.add_argument("--url", required=True)
    idx.add_argument("--cache-dir")

    # analyze
    ana = sub.add_parser("analyze", help="Score how usable a video is as an oracle")
    ana.add_argument("--url", required=True, help="YouTube URL of the candidate audio")
    ana.add_argument("--cache-dir", help="Directory for cached audio files")
    ana.add_argument("--json", action="store_true", help="Emit machine-readable JSON report")

    args = parser.parse_args()
    {
        "encode": _cmd_encode,
        "decode": _cmd_decode,
        "verify": _cmd_verify,
        "index": _cmd_index,
        "analyze": _cmd_analyze,
    }[args.command](args)


if __name__ == "__main__":
    main()
