from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import edge_tts

from utils.config import get_settings
from utils.logger import log

MAX_CHARS_PER_SUBTITLE = 16


@dataclass
class TTSResult:
    audio_path: str
    srt_path: str
    duration: float


class EdgeTTSEngine:
    """Text-to-speech using Microsoft Edge TTS (free, high quality)."""

    def __init__(self):
        settings = get_settings()
        tts_cfg = settings["tts"]
        self.voice = tts_cfg.get("voice", "zh-CN-YunxiNeural")
        self.rate = tts_cfg.get("rate", "+0%")
        self.volume = tts_cfg.get("volume", "+0%")

    async def _synthesize(self, text: str, output_path: str, srt_path: str) -> TTSResult:
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )

        submaker = edge_tts.SubMaker()

        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                else:
                    submaker.feed(chunk)

        raw_srt = submaker.get_srt()
        refined_srt = self._split_long_subtitles(raw_srt, MAX_CHARS_PER_SUBTITLE)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(refined_srt)

        duration = self._parse_srt_duration(refined_srt)
        log.info(f"TTS completed: {output_path} ({duration:.1f}s)")

        return TTSResult(audio_path=output_path, srt_path=srt_path, duration=duration)

    @staticmethod
    def _split_long_subtitles(srt_content: str, max_chars: int) -> str:
        """Split SRT entries that are too long into shorter segments."""
        blocks = re.split(r"\n\n+", srt_content.strip())
        new_blocks = []
        idx = 1

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            time_line = lines[1]
            text = "\n".join(lines[2:]).strip()

            if len(text) <= max_chars:
                new_blocks.append(f"{idx}\n{time_line}\n{text}")
                idx += 1
                continue

            match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", time_line)
            if not match:
                new_blocks.append(f"{idx}\n{time_line}\n{text}")
                idx += 1
                continue

            start_ms = EdgeTTSEngine._srt_to_ms(match.group(1))
            end_ms = EdgeTTSEngine._srt_to_ms(match.group(2))
            total_ms = end_ms - start_ms

            segments = EdgeTTSEngine._smart_split(text, max_chars)
            total_chars = sum(len(s) for s in segments)

            cursor_ms = start_ms
            for seg in segments:
                seg_ratio = len(seg) / max(total_chars, 1)
                seg_duration = int(total_ms * seg_ratio)
                seg_end = min(cursor_ms + seg_duration, end_ms)

                new_blocks.append(
                    f"{idx}\n"
                    f"{EdgeTTSEngine._ms_to_srt(cursor_ms)} --> {EdgeTTSEngine._ms_to_srt(seg_end)}\n"
                    f"{seg}"
                )
                idx += 1
                cursor_ms = seg_end

        return "\n\n".join(new_blocks) + "\n"

    @staticmethod
    def _smart_split(text: str, max_chars: int) -> list[str]:
        """Split text at natural break points (punctuation) into chunks <= max_chars."""
        break_chars = set("，。！？、；：,!?;:")
        segments = []
        current = ""

        for ch in text:
            current += ch
            if ch in break_chars and len(current) >= max_chars * 0.5:
                segments.append(current)
                current = ""
            elif len(current) >= max_chars:
                segments.append(current)
                current = ""

        if current:
            if segments and len(current) < max_chars * 0.3:
                segments[-1] += current
            else:
                segments.append(current)

        return segments

    @staticmethod
    def _srt_to_ms(ts: str) -> int:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)

    @staticmethod
    def _ms_to_srt(ms: int) -> str:
        h = ms // 3600000
        ms %= 3600000
        m = ms // 60000
        ms %= 60000
        s = ms // 1000
        ms %= 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _parse_srt_duration(srt_content: str) -> float:
        timestamps = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3})", srt_content)
        if not timestamps:
            return 0.0
        last = timestamps[-1]
        return EdgeTTSEngine._srt_to_ms(last) / 1000.0

    def synthesize(self, text: str, output_path: str, srt_path: str) -> TTSResult:
        return asyncio.run(self._synthesize(text, output_path, srt_path))


def create_tts_engine() -> EdgeTTSEngine:
    return EdgeTTSEngine()
