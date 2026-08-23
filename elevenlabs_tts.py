#!/usr/bin/env python3
"""Generate ElevenLabs audio plus character-level timing in one request.

This is a utility for the pipeline. It does not generate or animate video.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib import error, request


API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ElevenLabs TTS + alignment JSON")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--voice-id", default=os.getenv("ELEVENLABS_VOICE_ID"), help="ElevenLabs voice ID")
    parser.add_argument("--api-key", default=os.getenv("ELEVENLABS_API_KEY"), help="ElevenLabs API key")
    parser.add_argument("--model", default="eleven_multilingual_v2", help="TTS model")
    parser.add_argument("--audio-out", default="output/audio.mp3", help="Audio output path")
    parser.add_argument("--alignment-out", default="output/alignment.json", help="Alignment JSON output path")
    args = parser.parse_args()

    if not args.voice_id:
        parser.error("--voice-id is required or ELEVENLABS_VOICE_ID must be set")
    if not args.api_key:
        parser.error("--api-key is required or ELEVENLABS_API_KEY must be set")

    payload = json.dumps({
        "text": args.text,
        "model_id": args.model,
    }).encode("utf-8")

    url = API_URL.format(voice_id=args.voice_id)
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "xi-api-key": args.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"ElevenLabs HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except (error.URLError, TimeoutError) as exc:
        print(f"ElevenLabs request failed: {exc}", file=sys.stderr)
        return 1

    audio_b64 = data.get("audio_base64")
    alignment = data.get("alignment") or data.get("normalized_alignment")
    if not audio_b64:
        print("ElevenLabs response did not contain audio_base64", file=sys.stderr)
        return 1
    if not alignment:
        print("ElevenLabs response did not contain alignment", file=sys.stderr)
        return 1

    audio_path = Path(args.audio_out)
    alignment_path = Path(args.alignment_out)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    alignment_path.parent.mkdir(parents=True, exist_ok=True)

    audio_path.write_bytes(base64.b64decode(audio_b64))
    alignment_path.write_text(
        json.dumps({"alignment": alignment}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Audio:     {audio_path}")
    print(f"Alignment: {alignment_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
