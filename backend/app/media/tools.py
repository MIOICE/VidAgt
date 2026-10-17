from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings


class MediaCommandError(RuntimeError):
    pass


async def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    def execute() -> subprocess.CompletedProcess[str]:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            raise MediaCommandError(result.stderr[-4000:] or "media command failed")
        return result

    return await asyncio.to_thread(execute)


async def probe_video(path: Path) -> dict[str, Any]:
    result = await _run(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(result.stdout)
    duration_seconds = float(payload.get("format", {}).get("duration") or 0)
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    return {
        "duration_ms": int(duration_seconds * 1000),
        "format": payload.get("format", {}).get("format_name"),
        "video_codec": video_stream.get("codec_name"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
    }


async def sha256_file(path: Path) -> str:
    def calculate() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while block := handle.read(8 * 1024 * 1024):
                digest.update(block)
        return digest.hexdigest()

    return await asyncio.to_thread(calculate)


async def transcode_preview(source: Path, target: Path) -> None:
    await _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "25",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(target),
        ]
    )


async def extract_audio(source: Path, target: Path) -> None:
    await _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
    )


async def extract_keyframes(
    source: Path, output_dir: Path, duration_ms: int
) -> list[tuple[int, Path, float]]:
    def extract() -> list[tuple[int, Path, float]]:
        import cv2

        output_dir.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(str(source))
        duration_seconds = max(1.0, duration_ms / 1000)
        scan_interval = max(2.0, min(10.0, duration_seconds / settings.max_keyframes))
        results: list[tuple[int, Path, float]] = []
        previous_hist = None
        last_saved = -60.0
        timestamp = 0.0
        while timestamp <= duration_seconds and len(results) < settings.max_keyframes:
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = capture.read()
            if not ok:
                break
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            histogram = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
            cv2.normalize(histogram, histogram)
            difference = 1.0
            if previous_hist is not None:
                difference = 1.0 - float(
                    cv2.compareHist(previous_hist, histogram, cv2.HISTCMP_CORREL)
                )
            if previous_hist is None or difference >= 0.28 or timestamp - last_saved >= 60:
                frame_path = output_dir / f"frame_{int(timestamp * 1000):012d}.jpg"
                cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 86])
                results.append((int(timestamp * 1000), frame_path, max(0.0, difference)))
                last_saved = timestamp
            previous_hist = histogram
            timestamp += scan_interval
        capture.release()
        return results

    return await asyncio.to_thread(extract)


_whisper_models: dict[tuple[str, str, str], Any] = {}


async def transcribe_audio(audio_path: Path) -> list[dict[str, Any]]:
    def transcribe() -> list[dict[str, Any]]:
        import ctranslate2
        from faster_whisper import WhisperModel

        cuda_available = ctranslate2.get_cuda_device_count() > 0
        requested = settings.asr_device.lower()
        use_gpu = requested == "cuda" or (requested == "auto" and cuda_available)
        device = "cuda" if use_gpu else "cpu"
        model_name = settings.asr_model_gpu if use_gpu else settings.asr_model_cpu
        compute_type = settings.asr_compute_type_gpu if use_gpu else settings.asr_compute_type_cpu
        key = (model_name, device, compute_type)
        model = _whisper_models.get(key)
        if model is None:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            _whisper_models[key] = model
        segments, _ = model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return [
            {
                "start_ms": int(segment.start * 1000),
                "end_ms": int(segment.end * 1000),
                "text": segment.text.strip(),
            }
            for segment in segments
            if segment.text.strip()
        ]

    return await asyncio.to_thread(transcribe)

