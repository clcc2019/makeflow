from __future__ import annotations

import os
import random
import subprocess
from pathlib import Path

from utils.config import get_settings
from utils.logger import log


class PostProduction:
    """Video post-production: subtitle burn-in, BGM mixing, cover generation."""

    def __init__(self):
        self.settings = get_settings()
        self.sub_cfg = self.settings["post_production"]["subtitle"]
        self.bgm_cfg = self.settings["post_production"]["bgm"]
        self.cover_cfg = self.settings["post_production"]["cover"]

    def burn_subtitles(self, video_path: str, srt_path: str, output_path: str) -> str:
        """Burn SRT subtitles into video using FFmpeg."""
        if not Path(srt_path).exists():
            log.warning(f"SRT file not found: {srt_path}, skipping subtitles")
            return video_path

        abs_srt = str(Path(srt_path).resolve())
        srt_escaped = abs_srt.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        font_name = self.sub_cfg.get("font", "Noto Sans CJK SC")
        font_size = self.sub_cfg.get("font_size", 20)
        outline_width = self.sub_cfg.get("outline_width", 2)
        margin_bottom = self.sub_cfg.get("margin_bottom", 60)

        subtitle_filter = (
            f"subtitles='{srt_escaped}':force_style='"
            f"FontName={font_name},"
            f"FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"Outline={outline_width},"
            f"Shadow=1,"
            f"MarginV={margin_bottom},"
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

        log.info(f"Burning subtitles: {srt_path} -> {output_path}")
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        return output_path

    def mix_bgm(self, video_path: str, output_path: str, bgm_path: str | None = None) -> str:
        """Mix background music into video."""
        if not self.bgm_cfg.get("enabled", False):
            return video_path

        if bgm_path is None:
            bgm_path = self._pick_random_bgm()
        if bgm_path is None:
            log.warning("No BGM files available, skipping BGM")
            return video_path

        bgm_volume = self.bgm_cfg.get("volume", 0.08)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]aloop=loop=-1:size=2e+09,volume={bgm_volume}[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=3[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]

        log.info(f"Mixing BGM: {bgm_path} (volume={bgm_volume})")
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)
        return output_path

    def _pick_random_bgm(self) -> str | None:
        bgm_dir = Path(self.bgm_cfg.get("directory", "./assets/bgm"))
        if not bgm_dir.exists():
            return None
        files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav")) + list(bgm_dir.glob("*.m4a"))
        if not files:
            return None
        return str(random.choice(files))

    def generate_cover(self, video_path: str, title: str, output_path: str) -> str:
        """Extract a frame from video and overlay title text as cover image."""
        frame_path = output_path.replace(".png", "_frame.png")

        # Extract frame at 2 seconds
        cmd_frame = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", "2",
            "-vframes", "1",
            "-q:v", "2",
            frame_path,
        ]
        subprocess.run(cmd_frame, capture_output=True, timeout=30, check=True)

        try:
            self._overlay_title(frame_path, title, output_path)
        except Exception as e:
            log.warning(f"Title overlay failed, using raw frame: {e}")
            os.rename(frame_path, output_path)

        if Path(frame_path).exists() and frame_path != output_path:
            os.remove(frame_path)

        log.info(f"Cover generated: {output_path}")
        return output_path

    def _overlay_title(self, frame_path: str, title: str, output_path: str):
        """Overlay title text on frame using Pillow."""
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(frame_path)
        draw = ImageDraw.Draw(img)

        font_size = self.cover_cfg.get("title_font_size", 64)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("msyh.ttc", font_size)
            except Exception:
                font = ImageFont.load_default()

        max_width = img.width - 80
        lines = self._wrap_text(title, font, max_width, draw)
        text_block = "\n".join(lines)

        bbox = draw.multiline_textbbox((0, 0), text_block, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (img.width - text_w) // 2
        y = img.height // 2 - text_h // 2

        padding = 20
        draw.rectangle(
            [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
            fill=(0, 0, 0, 180),
        )

        draw.multiline_text(
            (x, y), text_block, font=font,
            fill=self.cover_cfg.get("title_color", "white"),
            align="center",
        )

        img.save(output_path, quality=95)

    @staticmethod
    def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
        lines = []
        current = ""
        for char in text:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def process(
        self,
        video_path: str,
        srt_path: str,
        title: str,
        task_dir: str,
    ) -> dict:
        """Full post-production pipeline."""
        task = Path(task_dir)

        subtitled_path = str(task / "video" / "subtitled.mp4")
        final_path = str(task / "video" / "final.mp4")
        cover_path = str(task / "cover" / "cover.png")

        current = video_path

        if Path(srt_path).exists():
            current = self.burn_subtitles(current, srt_path, subtitled_path)

        if self.bgm_cfg.get("enabled", False):
            bgm_output = final_path if current == subtitled_path else str(task / "video" / "bgm.mp4")
            current = self.mix_bgm(current, bgm_output)
            if current != final_path:
                os.rename(current, final_path)
                current = final_path
        else:
            if current != final_path:
                import shutil
                shutil.copy2(current, final_path)
                current = final_path

        self.generate_cover(current, title, cover_path)

        log.info(f"Post-production complete: {final_path}")
        return {
            "final_video_path": final_path,
            "cover_path": cover_path,
        }
