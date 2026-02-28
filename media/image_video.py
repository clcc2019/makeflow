"""Compose a narrated slideshow video from images + audio + subtitles."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils.logger import log


@dataclass
class ImageVideoResult:
    video_path: str
    duration: float


class ImageVideoComposer:
    """Composes a video from scene images + narration audio + SRT subtitles.

    Creates a Ken Burns effect (slow pan/zoom) slideshow with cross-dissolve
    transitions between scenes, overlaid with narration audio and subtitles.
    """

    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        transition_duration: float = 0.5,
    ):
        self.width = width
        self.height = height
        self.transition_duration = transition_duration

    def compose(
        self,
        image_paths: list[str],
        audio_path: str,
        srt_path: str,
        output_path: str,
        scene_durations: list[float] | None = None,
    ) -> ImageVideoResult:
        """Compose final video from images + audio + subtitles.

        If scene_durations is None, images are distributed evenly over the audio duration.
        """
        audio_duration = self._get_duration(audio_path)
        n = len(image_paths)

        if not scene_durations:
            per_scene = audio_duration / max(n, 1)
            scene_durations = [per_scene] * n

        log.info(f"Composing image video: {n} images, {audio_duration:.1f}s audio")

        raw_path = output_path.replace(".mp4", "_raw.mp4")
        self._build_slideshow(image_paths, scene_durations, raw_path)

        with_audio_path = output_path.replace(".mp4", "_audio.mp4")
        self._merge_audio(raw_path, audio_path, with_audio_path)

        if Path(srt_path).exists():
            from media.subtitle_burner import burn_subtitles
            burn_subtitles(
                video_path=with_audio_path,
                srt_path=srt_path,
                output_path=output_path,
                font_size=40,
                margin_bottom=220,
                video_width=self.width,
                video_height=self.height,
            )
        else:
            import shutil
            shutil.move(with_audio_path, output_path)

        for tmp in [raw_path, with_audio_path]:
            if Path(tmp).exists() and tmp != output_path:
                Path(tmp).unlink()

        duration = self._get_duration(output_path)
        log.info(f"Image video composed: {output_path} ({duration:.1f}s)")
        return ImageVideoResult(video_path=output_path, duration=duration)

    def _build_slideshow(
        self, image_paths: list[str], durations: list[float], output_path: str
    ):
        """Build slideshow using simple concat (fast, no GPU needed)."""
        self._build_simple_slideshow(image_paths, durations, output_path)

    def _build_simple_slideshow(
        self, image_paths: list[str], durations: list[float], output_path: str
    ):
        """Simple concat without transitions — fast and reliable."""
        temp_dir = Path(output_path).parent / "temp_slides"
        temp_dir.mkdir(exist_ok=True)

        segment_paths = []
        for i, (img, dur) in enumerate(zip(image_paths, durations)):
            seg_path = str((temp_dir / f"seg_{i:03d}.ts").resolve())
            abs_img = str(Path(img).resolve())
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", abs_img,
                "-t", f"{dur}",
                "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                       f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-r", "25",
                "-f", "mpegts",
                seg_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                log.warning(f"Segment {i} encode failed: {result.stderr[:200]}")
                raise RuntimeError(f"FFmpeg segment encode failed for {img}")
            segment_paths.append(seg_path)
            log.info(f"  Segment {i+1}/{len(image_paths)} encoded ({dur:.1f}s)")

        concat_input = "concat:" + "|".join(segment_paths)
        cmd = [
            "ffmpeg", "-y",
            "-i", concat_input,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log.error(f"Concat failed: {result.stderr[:300]}")
            raise RuntimeError("FFmpeg concat failed")

        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    def _merge_audio(self, video_path: str, audio_path: str, output_path: str):
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)

    def _burn_subtitles(self, video_path: str, srt_path: str, output_path: str):
        abs_srt = str(Path(srt_path).resolve())
        srt_escaped = abs_srt.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

        # original_size matches video resolution so FontSize is in real pixels
        subtitle_filter = (
            f"subtitles='{srt_escaped}':"
            f"original_size={self.width}x{self.height}:"
            f"force_style='"
            f"FontName=Noto Sans CJK SC,"
            f"FontSize=38,"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"Outline=3,"
            f"Shadow=1,"
            f"MarginV=200,"
            f"Alignment=2'"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", subtitle_filter,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log.warning(f"Subtitle burn failed: {result.stderr[:300]}")
            import shutil
            shutil.copy2(video_path, output_path)

    @staticmethod
    def _get_duration(path: str) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0
