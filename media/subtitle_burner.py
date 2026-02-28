"""Burn SRT subtitles onto video using drawtext filter for precise positioning."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils.logger import log

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


@dataclass
class SrtEntry:
    index: int
    start_sec: float
    end_sec: float
    text: str


def parse_srt(srt_path: str) -> list[SrtEntry]:
    """Parse an SRT file into a list of entries."""
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())
    entries = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue

        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            lines[1],
        )
        if not time_match:
            continue

        g = time_match.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        text = " ".join(lines[2:]).strip()

        entries.append(SrtEntry(index=idx, start_sec=start, end_sec=end, text=text))

    return entries


def burn_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_size: int = 40,
    margin_bottom: int = 220,
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """Burn subtitles using FFmpeg drawtext — pixel-precise positioning.

    Each SRT entry becomes a drawtext filter with enable='between(t,start,end)',
    positioned at fixed bottom center.
    """
    entries = parse_srt(srt_path)
    if not entries:
        log.warning("No SRT entries found, skipping subtitle burn")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    font_escaped = FONT_PATH.replace(":", "\\:")
    y_pos = video_height - margin_bottom

    drawtext_filters = []
    for e in entries:
        text_escaped = (
            e.text
            .replace("\\", "\\\\")
            .replace("'", "\u2019")
            .replace(":", "\\:")
            .replace("%", "%%")
        )
        dt = (
            f"drawtext=fontfile='{font_escaped}':"
            f"text='{text_escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"borderw=3:"
            f"bordercolor=black:"
            f"shadowx=2:shadowy=2:shadowcolor=black@0.5:"
            f"x=(w-text_w)/2:"
            f"y={y_pos}:"
            f"enable='between(t,{e.start_sec:.3f},{e.end_sec:.3f})'"
        )
        drawtext_filters.append(dt)

    vf = ",".join(drawtext_filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]

    log.info(f"Burning {len(entries)} subtitle entries with drawtext")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        log.error(f"drawtext subtitle burn failed: {result.stderr[:500]}")
        import shutil
        shutil.copy2(video_path, output_path)
    else:
        log.info(f"Subtitles burned: {output_path}")

    return output_path
