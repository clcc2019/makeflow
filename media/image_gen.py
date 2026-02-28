"""AI image generation for video scenes. Falls back to styled info-graphics."""
from __future__ import annotations

import math
import random
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from utils.config import get_settings
from utils.logger import log

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_BLACK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
FONT_REGULAR = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

SCENE_THEMES = {
    "explosion": {"bg": (30, 10, 10), "accent": (220, 60, 40), "icon": "💥"},
    "military": {"bg": (10, 20, 30), "accent": (60, 140, 200), "icon": "⚔️"},
    "diplomacy": {"bg": (20, 20, 35), "accent": (180, 160, 60), "icon": "🤝"},
    "defense": {"bg": (15, 25, 15), "accent": (80, 180, 80), "icon": "🛡️"},
    "economy": {"bg": (25, 10, 10), "accent": (200, 80, 60), "icon": "📉"},
    "alert": {"bg": (35, 15, 10), "accent": (240, 120, 30), "icon": "⚠️"},
    "default": {"bg": (18, 18, 32), "accent": (100, 140, 220), "icon": "📰"},
}


class ImageGenerator:
    """Generate images for video scenes. Uses API when available, styled placeholders otherwise."""

    def __init__(self):
        settings = get_settings()
        llm_cfg = settings["llm"]
        provider = llm_cfg["default_provider"]
        provider_cfg = llm_cfg["providers"][provider]
        self.api_key = provider_cfg["api_key"]
        self.base_url = provider_cfg.get("base_url", "https://api.openai.com/v1")
        self.timeout = 120

    def generate(
        self,
        prompt: str,
        output_path: str,
        size: str = "1024x1792",
        narration: str = "",
        scene_id: int = 0,
        total_scenes: int = 1,
    ) -> str:
        """Generate an image. Try API first, fall back to styled info-graphic."""
        if not self.api_key or "${" in self.api_key:
            return self._create_news_infographic(prompt, narration, output_path, scene_id, total_scenes)

        try:
            return self._generate_api(prompt, output_path, size)
        except Exception as e:
            log.warning(f"API image generation failed: {e}")
            return self._create_news_infographic(prompt, narration, output_path, scene_id, total_scenes)

    def _generate_api(self, prompt: str, output_path: str, size: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": "dall-e-3", "prompt": prompt, "n": 1, "size": size, "response_format": "url"}
        resp = httpx.post(f"{self.base_url.rstrip('/')}/images/generations", headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        image_url = resp.json()["data"][0]["url"]
        img_resp = httpx.get(image_url, timeout=60)
        img_resp.raise_for_status()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        log.info(f"API image saved: {output_path}")
        return output_path

    def _create_news_infographic(
        self, prompt: str, narration: str, output_path: str, scene_id: int, total_scenes: int
    ) -> str:
        """Create a visually compelling news infographic with Chinese text."""
        W, H = 1080, 1920
        theme = self._pick_theme(prompt)
        bg = theme["bg"]
        accent = theme["accent"]

        img = Image.new("RGB", (W, H), color=bg)
        draw = ImageDraw.Draw(img)

        # Gradient background
        for y in range(H):
            ratio = y / H
            r = int(bg[0] * (1 - ratio * 0.4) + accent[0] * ratio * 0.15)
            g = int(bg[1] * (1 - ratio * 0.4) + accent[1] * ratio * 0.15)
            b = int(bg[2] * (1 - ratio * 0.4) + accent[2] * ratio * 0.15)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Geometric decorations
        self._draw_decorations(draw, W, H, accent)

        # Top bar: "BREAKING NEWS" style
        bar_h = 120
        draw.rectangle([0, 0, W, bar_h], fill=accent)
        font_bar = self._load_font(FONT_BLACK, 52)
        bar_text = "突发新闻" if scene_id <= 1 else f"深度解析 {scene_id}/{total_scenes}"
        bbox = draw.textbbox((0, 0), bar_text, font=font_bar)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, (bar_h - 52) // 2), bar_text, fill="white", font=font_bar)

        # Side accent line
        draw.rectangle([0, bar_h, 8, H], fill=accent)

        # Main narration text (the key content)
        display_text = narration if narration else self._extract_chinese(prompt)
        if display_text:
            font_main = self._load_font(FONT_BOLD, 58)
            lines = self._wrap_text(display_text, font_main, W - 140, draw)

            y_start = 300
            line_height = 90

            # Semi-transparent background panel for text
            text_block_h = len(lines) * line_height + 80
            panel = Image.new("RGBA", (W - 80, text_block_h), (0, 0, 0, 140))
            img.paste(Image.alpha_composite(
                Image.new("RGBA", panel.size, (0, 0, 0, 0)), panel
            ).convert("RGB"), (40, y_start - 40))
            draw = ImageDraw.Draw(img)

            for i, line in enumerate(lines):
                y = y_start + i * line_height
                # Text shadow
                draw.text((72, y + 3), line, fill=(0, 0, 0), font=font_main)
                draw.text((70, y), line, fill="white", font=font_main)

        # Bottom info bar
        bottom_y = H - 160
        draw.rectangle([0, bottom_y, W, H], fill=(0, 0, 0, 180))
        font_small = self._load_font(FONT_REGULAR, 32)
        draw.text((40, bottom_y + 20), "2026年2月28日 | 国际快讯", fill=(200, 200, 200), font=font_small)

        # Scene indicator dots
        dot_y = bottom_y + 80
        dot_start_x = (W - total_scenes * 30) // 2
        for i in range(total_scenes):
            x = dot_start_x + i * 30
            color = accent if i == scene_id - 1 else (80, 80, 80)
            draw.ellipse([x, dot_y, x + 16, dot_y + 16], fill=color)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, quality=95)
        log.info(f"News infographic created: {output_path}")
        return output_path

    def _pick_theme(self, prompt: str) -> dict:
        prompt_lower = prompt.lower()
        if any(w in prompt_lower for w in ["explosion", "bomb", "strike", "attack", "fire"]):
            return SCENE_THEMES["explosion"]
        if any(w in prompt_lower for w in ["military", "carrier", "fighter", "navy", "army", "f-22"]):
            return SCENE_THEMES["military"]
        if any(w in prompt_lower for w in ["diplomacy", "negotiation", "talks", "peace"]):
            return SCENE_THEMES["diplomacy"]
        if any(w in prompt_lower for w in ["defense", "iron dome", "intercept", "missile"]):
            return SCENE_THEMES["defense"]
        if any(w in prompt_lower for w in ["stock", "market", "oil", "economy", "price"]):
            return SCENE_THEMES["economy"]
        if any(w in prompt_lower for w in ["alert", "warning", "evacuat"]):
            return SCENE_THEMES["alert"]
        return SCENE_THEMES["default"]

    def _draw_decorations(self, draw: ImageDraw.Draw, w: int, h: int, accent: tuple):
        """Draw subtle geometric decorations."""
        # Diagonal lines
        for i in range(6):
            x_offset = random.randint(0, w)
            y_offset = random.randint(200, h - 200)
            faded = tuple(c // 6 for c in accent)
            draw.line([(x_offset, y_offset), (x_offset + 300, y_offset - 200)], fill=faded, width=2)

        # Corner brackets
        bracket_color = tuple(c // 3 for c in accent)
        sz = 60
        # Top-right
        draw.line([(w - sz - 30, 140), (w - 30, 140), (w - 30, 140 + sz)], fill=bracket_color, width=3)
        # Bottom-left
        draw.line([(30, h - 180 - sz), (30, h - 180), (30 + sz, h - 180)], fill=bracket_color, width=3)

    @staticmethod
    def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            try:
                return ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", size)
            except Exception:
                return ImageFont.load_default()

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

    @staticmethod
    def _extract_chinese(text: str) -> str:
        """Extract any Chinese characters from text, or return the first 40 chars."""
        import re
        chinese = re.findall(r'[\u4e00-\u9fff\uff01-\uff5e\u3000-\u303f]+', text)
        if chinese:
            return "".join(chinese)
        return text[:40]


def create_image_generator() -> ImageGenerator:
    return ImageGenerator()
