# TellMeWords

**Zero-payload steganography via opportunistic codebook derivation.**

No carrier file is ever modified. The message is not hidden — it is *found*.

---

## The Idea

Classical steganography embeds secret bits into a carrier file by overwriting its least-significant bits. The artifact is detectable: the modified file differs from the original.

TellMeWords inverts this model entirely.

A public, unmodified YouTube audio file (a Vocaloid track, a synthesizer piece) acts as a **shared random oracle**. The sender scans its existing LSB stream and locates positions where the audio's natural bit patterns already spell out the target message. Those coordinates — together with a Reed-Solomon error correction header — are packaged into a JSON file disguised as UTAU vocal synthesizer tuning metadata and posted to a GitHub Gist.

The receiver fetches the Gist, downloads the same YouTube audio, reads the bits at the listed positions, and reconstructs the plaintext. No file was altered. No steganographic artifact exists. There is nothing to detect.

```
Sender                          Gist (public)          Receiver
──────                          ─────────────          ────────
YouTube audio ─┐                                ┌─ YouTube audio
               │  derive coords                 │  apply coords
               └──────────────► config.json ───►┘
                                (UTAU disguise)
               ↑                                ↑
          same oracle,                     same oracle,
          never modified                   never modified
```

---

## Why This Works

A 4-minute stereo audio file at 44100 Hz contains approximately **12 million LSB samples**. Grouped into 8-bit windows, each of the 256 possible byte values appears roughly **46,875 times** by chance — placed there by physics, compression artifacts, and synthesis noise.

The byte `h` (0x68) already exists in the audio at tens of thousands of positions. So does `e`, `l`, `o`. Every short message already exists, simultaneously, scattered throughout the file.

Encoding is a lookup: for each message byte, record *where* that byte naturally occurs. Decoding is index access: read back the bits at those positions. The audio is untouched throughout.

Reed-Solomon error correction handles minor divergence between sender and receiver downloads (different CDN nodes, ffmpeg version rounding). Hamming-distance tolerance in the codebook lookup (`--hamming 1|2`) extends coverage to near-matches, storing a one-byte correction mask in the config.

---

## Prior Art Comparison

| System | Carrier origin | Carrier modified? | Key required? |
|---|---|---|---|
| Classical LSB stego | Sender chooses | **Yes** | No |
| Wet paper codes | Sender chooses | Partially | No |
| Mimic functions | Sender synthesizes | N/A | No |
| OTP | Shared random tape | N/A | Yes |
| **TellMeWords** | **Third-party public** | **No** | **No** |

The carrier is not produced by the sender. The sender cannot modify it even in principle — it is a third-party artifact on YouTube's servers. This is the core distinction from all prior work.

---

## Threat Model

| Scenario | Result |
|---|---|
| Adversary intercepts the Gist alone | Sees plausible UTAU tuning JSON. No message recoverable. |
| Adversary has Gist + YouTube URL | **Full break.** Message is recoverable. By design — no cryptographic protection. |
| Audio re-encoded by YouTube CDN | SHA-256 stored in config detects divergence; decode aborts cleanly. |
| Statistical analysis of config values | Coordinate distribution is detectable without mitigation (Phase-2 smoothness constraint addresses this). |

This system provides **plausible deniability**, not cryptographic secrecy. If confidentiality is required, encrypt the plaintext before passing it to TellMeWords.

---

## Installation

Requires Python 3.11+ and [ffmpeg](https://ffmpeg.org/).

```bash
brew install ffmpeg          # macOS
# apt install ffmpeg         # Debian/Ubuntu

git clone https://github.com/yourname/tellmewords
cd tellmewords
uv venv && uv pip install -r requirements.txt
```

---

## Usage

### Encode

```bash
# Write config JSON to stdout
tellmewords encode --url "https://www.youtube.com/watch?v=<id>" --message "secret"

# Save config to file
tellmewords encode --url "https://www.youtube.com/watch?v=<id>" --message "secret" -o config.json

# Upload directly to GitHub Gist
tellmewords encode --url "https://www.youtube.com/watch?v=<id>" --message "secret" \
  --gist-token $GITHUB_TOKEN

# With Hamming-1 tolerance (larger candidate pool, stores correction mask)
tellmewords encode --url "..." --message "secret" --hamming 1
```

### Decode

```bash
# From a Gist URL
tellmewords decode --gist "https://gist.github.com/..."

# From a local file (any extension — .json, .ustx, anything)
tellmewords decode --config-file tuning.ustx

# From stdin
cat config.json | tellmewords decode
```

### Verify audio integrity

```bash
tellmewords verify --gist "https://gist.github.com/..."
```

### Pre-cache audio (speeds up repeated encodes against the same track)

```bash
tellmewords index --url "https://www.youtube.com/watch?v=<id>" --cache-dir ~/.tellmewords
```

---

## Demo

```bash
# Offline demo (no YouTube, uses synthetic audio)
python demo/demo.py --offline

# Live demo
python demo/demo.py --url "https://www.youtube.com/watch?v=<id>" \
  --message "BlackHat2026" --gist-token $GITHUB_TOKEN
```

Expected output:

```
╔══════════════════════════════════════════════════════════════╗
║         TellMeWords: Zero-Payload Steganography Demo         ║
║  Nothing is hidden. Nothing is modified. Yet here we are.    ║
╚══════════════════════════════════════════════════════════════╝

  [1] Oracle audio: https://www.youtube.com/watch?v=...
  [2] Tuning config generated. Here's what the adversary sees:
      { "ustx_version": "0.6", "name": "ghost_comet_tuning_yvgb", ...
  [5] Recovered message:
      ┌─────────────────────────────────────────┐
      │  BlackHat2026                           │
      └─────────────────────────────────────────┘
  [6] What did we modify?
      Nothing. The message was always there — we just knew where to look.
```

---

## How the Tuning Config Is Disguised

The coordinate list is serialized as a UTAU `.ustx`-style JSON document. A real UTAU tuning file contains BPM, phoneme sequences, per-note pitch correction curves (PBY arrays), velocity, and envelope shapes. TellMeWords config maps onto these fields:

| TellMeWords field | UTAU field | Notes |
|---|---|---|
| Sample position (low 16 bits) | `notes[i].pbys` | Pitch bend Y value |
| Sample position (high bits) | `notes[i].pbys_offset` | Coarse tuning offset |
| Correction mask | `notes[i].velocity` | 0 for exact matches |
| YouTube URL | `track_source.url` | Source track reference |
| Audio SHA-256 | `track_source.checksum` | Render reference hash |
| Hamming tolerance | `engine_params.tolerance_mode` | Tuning mode flag |
| RS parity count | `engine_params.reverb_tail` | Reverb tail length |

A real UTAU tuning export for a 2-minute song contains 100–200 notes. A TellMeWords config for a 100-byte message contains ~130 entries — indistinguishable in structure.

---

## Repository Structure

```
tellmewords/
├── tellmewords/
│   ├── audio.py       # Download (yt-dlp API), PCM decode, RMS segmentation
│   ├── codebook.py    # Inverted index construction, encode, decode
│   ├── config.py      # TuningConfig dataclass, UTAU JSON schema, Gist I/O
│   ├── ec.py          # Reed-Solomon encode/decode (reedsolo)
│   ├── sender.py      # Encode pipeline
│   ├── receiver.py    # Decode pipeline
│   └── __main__.py    # CLI entry point
├── demo/
│   └── demo.py        # BlackHat demo script (--offline mode included)
└── tests/
    ├── test_roundtrip.py      # End-to-end encode → decode
    ├── test_ec.py             # Reed-Solomon correctness
    ├── test_audio.py          # Segmentation logic
    ├── test_config.py         # UTAU JSON schema round-trips
    └── test_crossplatform.py  # Determinism across runs
```

---

## Running Tests

```bash
# All offline tests (no YouTube required)
pytest tests/ -m "not network"

# With network (requires real YouTube access)
pytest tests/ -m network
```

---

## Academic Framing

**Novel claim:** Zero-payload reference steganography. The carrier is a third-party public artifact. The sender never possesses, controls, or modifies it. The message is a navigation instruction set over a pre-existing source of public entropy.

**One-sentence pitch:**
> *TellMeWords hides messages by telling the receiver where to look in a public YouTube video (not by changing it) making the carrier impossible to detect as modified because it never was.*

**Presented at:** *(your venue here)*

---

## License

MIT
