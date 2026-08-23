# Deterministic 2D Phoneme Lip-Sync

This project turns an ElevenLabs TTS track into a 2D avatar video **without generative video AI**.

The renderer only does three things:

1. reads the character-level timing returned by ElevenLabs,
2. maps vowels to pre-drawn mouth PNGs,
3. composites the PNGs frame-by-frame and encodes the result with FFmpeg.

ElevenLabs currently exposes a `POST /v1/text-to-speech/:voice_id/with-timestamps` endpoint that returns the generated audio together with character start/end times. This project consumes that timing JSON; the animation itself is deterministic. See: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps

## Assets

Put these files in `assets/` and make all six PNGs use the **exact same canvas size and mouth position**:

```text
assets/
├── avatar.png
├── mouth_neutral.png
├── mouth_A.png
├── mouth_I.png
├── mouth_O.png
└── mouth_U.png
```

The mouth PNGs should normally be transparent full-canvas images containing only the mouth pixels. `render_avatar.py` overlays them directly over `avatar.png`.

## Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

FFmpeg and FFprobe must also be installed and available on `PATH`.

On Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

## Input alignment JSON

The renderer accepts either the full ElevenLabs `with-timestamps` response or just its `alignment` object.

Example:

```json
{
  "alignment": {
    "characters": ["H", "a", "l", "l", "o"],
    "character_start_times_seconds": [0.0, 0.08, 0.15, 0.21, 0.28],
    "character_end_times_seconds": [0.08, 0.15, 0.21, 0.28, 0.38]
  }
}
```

## Render

```bash
python render_avatar.py \
  --audio input/audio.mp3 \
  --alignment input/alignment.json \
  --avatar assets/avatar.png \
  --output output/avatar.mp4
```

The default is 30 FPS and a black background.

For a different background:

```bash
python render_avatar.py \
  --audio input/audio.mp3 \
  --alignment input/alignment.json \
  --background 111111 \
  --output output/avatar.mp4
```

## How the mouth mapping works

The current asset set only has four vowel shapes plus neutral:

```text
A / Ä -> mouth_A
E       -> mouth_I (approximation because there is no E asset)
I / Y   -> mouth_I
O / Ö   -> mouth_O
U / Ü   -> mouth_U
all other characters -> mouth_neutral
```

This is intentionally simple and deterministic. Add dedicated `mouth_E.png` and update `CHAR_TO_MOUTH` in `render_avatar.py` later if you want a more natural result.

## Recommended automation

For your end-to-end pipeline, generate TTS through ElevenLabs' timestamps endpoint rather than creating a plain MP3 first and then trying to rediscover timing from the audio. Save both outputs:

```text
text
  ↓
ElevenLabs /with-timestamps
  ├── audio.mp3
  └── alignment.json
            ↓
   render_avatar.py
            ↓
        avatar.mp4
```

That keeps the lip-sync stage free from speech-recognition or video-generation models.

## Transparency note

H.264 MP4 does not preserve an alpha channel in the normal `yuv420p` workflow used here, so the generated MP4 has an opaque background. If the final editor needs a transparent avatar overlay, use a WebM/VP9 or ProRes 4444 render path instead of H.264 MP4.
