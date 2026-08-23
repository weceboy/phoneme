# Deterministic 2D Phoneme Lip-Sync

This project turns an ElevenLabs TTS track into a 2D avatar video **without generative video AI**.

The renderer only does three things:

1. reads the character-level timing returned by ElevenLabs,
2. maps vowels to pre-drawn mouth PNGs,
3. composites the PNGs frame-by-frame and encodes the result with FFmpeg.

ElevenLabs currently exposes a `POST /v1/text-to-speech/:voice_id/with-timestamps` endpoint that returns the generated audio together with character start/end times. This project consumes that timing JSON; the animation itself is deterministic. See: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps

## Assets

Put these files in the repository root (or pass a different avatar path):

```text
avatar.png
mouth_neutral.png
mouth_A.png
mouth_I.png
mouth_O.png
mouth_U.png
```

The mouth PNGs should be transparent images with the **exact same canvas size and mouth position** as `avatar.png`. The renderer overlays them directly over the avatar.

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

## Option A: You already have an MP3

Your ElevenLabs step should also save the timestamp response as `alignment.json`. The renderer accepts either the full response or just the `alignment` object.

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

Render:

```bash
python render_avatar.py \
  --audio audio.mp3 \
  --alignment alignment.json \
  --avatar avatar.png \
  --output output/avatar.mp4
```

The default is 30 FPS and a black background.

## Option B: Let this repository create the TTS + timing

Set your credentials:

```bash
export ELEVENLABS_API_KEY="..."
export ELEVENLABS_VOICE_ID="..."
```

Then:

```bash
python elevenlabs_tts.py \
  --text "Hallo, das ist mein automatisch erzeugtes Video." \
  --audio-out output/audio.mp3 \
  --alignment-out output/alignment.json
```

Then render the avatar:

```bash
python render_avatar.py \
  --audio output/audio.mp3 \
  --alignment output/alignment.json \
  --avatar avatar.png \
  --output output/avatar.mp4
```

This uses ElevenLabs' timestamp-producing TTS endpoint once, so the same TTS audio and timing data are used for the animation. No speech recognition or video generation is performed by this repository.

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

This is intentionally simple and deterministic. Add a dedicated `mouth_E.png` later and update `CHAR_TO_MOUTH` if you want more accurate phoneme coverage.

## Full automation

```text
LLM
 ↓
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

The only external generation step is your TTS. The avatar animation and MP4 rendering are local and deterministic.

## Transparency note

H.264 MP4 does not preserve an alpha channel in the normal `yuv420p` workflow used here, so the generated MP4 has an opaque background. For a later B-roll compositing step where you need a transparent avatar, a WebM/VP9 or ProRes 4444 output is the better intermediate format.
