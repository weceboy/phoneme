#!/usr/bin/env python3
"""Render a deterministic 2D mouth animation from ElevenLabs character timings.

No video/image generation model is used. The animation is made by compositing
pre-rendered transparent mouth PNGs onto a transparent avatar PNG and encoding
the resulting frames with FFmpeg.

Expected assets (by default beside the avatar):
    avatar.png
    mouth_neutral.png
    mouth_A.png
    mouth_E.png
    mouth_I.png
    mouth_O.png
    mouth_U.png

The alignment JSON can be the response from ElevenLabs' /with-timestamps
endpoint, or a file containing an object with an `alignment` field.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


MOUTH_FILES = {
    "neutral": "mouth_neutral.png",
    "A": "mouth_A.png",
    "E": "mouth_E.png",
    "I": "mouth_I.png",
    "O": "mouth_O.png",
    "U": "mouth_U.png",
}

CHAR_TO_MOUTH = {
    **{c: "A" for c in "aAäÄàÀáÁâÂåÅ"},
    **{c: "E" for c in "eEéÉèÈêÊëË"},
    **{c: "I" for c in "iIyYïÏîÎìÌíÍ"},
    **{c: "O" for c in "oOöÖòÒóÓôÔõÕøØ"},
    **{c: "U" for c in "uUüÜùÙúÚûÛ"},
}


class RenderError(RuntimeError):
    pass


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RenderError(
            f"Required executable not found: {cmd[0]!r}. Install it and make sure it is on PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RenderError(f"Command failed: {' '.join(cmd)}\n{detail}") from exc


def require_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise RenderError(f"{name} is required but was not found on PATH.")


def ffprobe_duration(audio: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ]
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RenderError(f"Could not read duration from {audio}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RenderError(f"Audio duration is invalid: {duration}")
    return duration


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"Could not read alignment JSON: {path}") from exc
    if not isinstance(data, dict):
        raise RenderError("Alignment JSON root must be an object.")
    return data


def extract_alignment(data: dict[str, Any]) -> dict[str, Any]:
    alignment = data.get("alignment")
    if isinstance(alignment, dict):
        return alignment
    normalized = data.get("normalized_alignment")
    if isinstance(normalized, dict):
        return normalized
    if "characters" in data:
        return data
    raise RenderError("No `alignment`, `normalized_alignment`, or `characters` object found in JSON.")


def build_vowel_events(alignment: dict[str, Any], duration: float) -> list[tuple[float, float, str]]:
    characters = alignment.get("characters")
    starts = alignment.get("character_start_times_seconds")
    ends = alignment.get("character_end_times_seconds")

    if not isinstance(characters, list) or not isinstance(starts, list) or not isinstance(ends, list):
        raise RenderError("Alignment must contain characters, character_start_times_seconds and character_end_times_seconds arrays.")
    if not (len(characters) == len(starts) == len(ends)):
        raise RenderError("Alignment arrays have different lengths.")

    events: list[tuple[float, float, str]] = []
    for char, start, end in zip(characters, starts, ends):
        if not isinstance(char, str) or not char:
            continue
        mouth = CHAR_TO_MOUTH.get(char[0])
        if mouth is None:
            continue
        try:
            start_f = max(0.0, float(start))
            end_f = min(duration, float(end))
        except (TypeError, ValueError):
            continue
        if end_f > start_f:
            events.append((start_f, end_f, mouth))

    return events


def sample_events(
    events: list[tuple[float, float, str]],
    frame_time: float,
    minimum_hold: float,
    last_mouth: str,
) -> str:
    for start, end, mouth in events:
        if start <= frame_time < end:
            return mouth
    if last_mouth != "neutral":
        for start, end, mouth in reversed(events):
            if start <= frame_time and frame_time - end < minimum_hold and mouth == last_mouth:
                return mouth
    return "neutral"


def parse_hex_color(value: str) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("Background color must be RRGGBB, e.g. 000000")
    try:
        rgb = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Background color must be hexadecimal RRGGBB") from exc
    return (*rgb, 255)


def load_asset(path: Path, target_size: tuple[int, int] | None = None) -> Image.Image:
    if not path.exists():
        raise RenderError(f"Missing asset: {path}")
    image = Image.open(path).convert("RGBA")
    if target_size is not None and image.size != target_size:
        raise RenderError(
            f"Asset {path.name} has size {image.size}, expected {target_size}. "
            "Generate all mouth PNGs on the same canvas as avatar.png."
        )
    return image


def encode_mp4(frames_dir: Path, audio: Path, output: Path, fps: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(frames_dir / "frame_%06d.png"),
            "-i",
            str(audio),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def render(args: argparse.Namespace) -> None:
    require_binary("ffmpeg")
    require_binary("ffprobe")

    audio = Path(args.audio).resolve()
    alignment_path = Path(args.alignment).resolve()
    avatar_path = Path(args.avatar).resolve()
    output = Path(args.output).resolve()

    if not audio.exists():
        raise RenderError(f"Audio not found: {audio}")

    alignment = extract_alignment(load_json(alignment_path))
    duration = ffprobe_duration(audio)

    avatar = load_asset(avatar_path)
    mouth_images: dict[str, Image.Image] = {}
    for key, filename in MOUTH_FILES.items():
        mouth_images[key] = load_asset(avatar_path.parent / filename, avatar.size)

    events = build_vowel_events(alignment, duration)
    if not events:
        print("Warning: no vowel events found; rendering neutral mouth only.", file=sys.stderr)

    frame_count = max(1, math.ceil(duration * args.fps))
    frames_dir = output.parent / f".{output.stem}_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    background = args.background
    bg_rgba = None if background.lower() == "transparent" else parse_hex_color(background)

    last_mouth = "neutral"
    try:
        for index in range(frame_count):
            t = index / args.fps
            mouth_name = sample_events(events, t, args.hold, last_mouth)
            last_mouth = mouth_name

            if bg_rgba is None:
                frame = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
            else:
                frame = Image.new("RGBA", avatar.size, bg_rgba)

            frame.alpha_composite(avatar)
            frame.alpha_composite(mouth_images.get(mouth_name, mouth_images["neutral"]))
            frame.convert("RGB").save(frames_dir / f"frame_{index + 1:06d}.png")

        encode_mp4(frames_dir, audio, output, args.fps)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"Rendered: {output}")
    print(f"Duration: {duration:.3f}s")
    print(f"Frames:   {frame_count}")
    print(f"Vowels:   {len(events)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a deterministic 2D lip-sync MP4 from an avatar PNG, mouth PNGs and ElevenLabs timings."
    )
    parser.add_argument("--audio", required=True, help="Input MP3/WAV/M4A audio file")
    parser.add_argument("--alignment", required=True, help="ElevenLabs alignment JSON file")
    parser.add_argument("--avatar", default="avatar.png", help="Avatar PNG (default: avatar.png)")
    parser.add_argument("--output", default="output/avatar.mp4", help="Output MP4 path")
    parser.add_argument("--fps", type=int, default=30, help="Output frame rate (default: 30)")
    parser.add_argument(
        "--hold",
        type=float,
        default=0.025,
        help="Keep a vowel mouth open this long after its timing ends to reduce flicker (default: 0.025s)",
    )
    parser.add_argument(
        "--background",
        default="000000",
        help="RRGGBB background color, or 'transparent' for transparent frame generation (MP4 will still be opaque)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.fps <= 0:
        parser.error("--fps must be > 0")
    if args.hold < 0:
        parser.error("--hold must be >= 0")
    try:
        render(args)
    except RenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
