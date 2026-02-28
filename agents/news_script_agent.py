"""Generates segmented news scripts with scene-by-scene image prompts."""
from __future__ import annotations

from dataclasses import dataclass, field

from utils.llm_client import get_llm
from utils.logger import log


@dataclass
class NewsScene:
    """A single scene in a news video."""
    scene_id: int
    narration: str
    image_prompt: str
    duration_hint: float = 0.0


@dataclass
class NewsScript:
    title: str
    scenes: list[NewsScene]
    full_narration: str
    publish_title: str
    tags: list[str]
    word_count: int = 0


class NewsScriptAgent:
    """Generates news video scripts with per-scene narration and image prompts."""

    SYSTEM_PROMPT = """你是一位资深的国际新闻短视频编导。你需要把新闻事件编排成适合短视频播放的分镜脚本。

要求：
- 语言口语化但专业、客观
- 信息密度高，节奏紧凑
- 每个场景配一段解说词 + 一段英文配图描述（用于AI生图）
- 配图描述必须是写实新闻风格，不含真实人名，描述场景和氛围
- 全程使用中文解说，配图提示词用英文"""

    SCRIPT_PROMPT = """请根据以下新闻素材，创建一个60-90秒的短视频分镜脚本。

新闻标题：{title}

新闻素材：
{news_content}

要求：
1. 拆分为5-7个场景，每个场景10-15秒
2. 开头第一个场景必须是震撼的hook（吸引注意力）
3. 最后一个场景是总结和展望
4. 每个场景包含：解说词（中文）+ 配图描述（英文，写实新闻摄影风格）
5. 配图描述不要包含任何真实政治人物的姓名，用职位描述代替
6. 解说词总字数250-400字

以JSON格式返回：
{{
  "publish_title": "视频标题（20字以内，震撼有力）",
  "tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5"],
  "scenes": [
    {{
      "scene_id": 1,
      "narration": "这个场景的中文解说词",
      "image_prompt": "Photojournalistic style, realistic: description of the scene in English, dramatic lighting, 4K quality, news photography"
    }}
  ]
}}"""

    def __init__(self, llm_provider: str | None = None):
        self.llm = get_llm(llm_provider)

    def generate(self, title: str, news_content: str) -> NewsScript:
        prompt = self.SCRIPT_PROMPT.format(
            title=title,
            news_content=news_content,
        )

        log.info(f"Generating news script: {title}")
        result = self.llm.chat_json(prompt=prompt, system=self.SYSTEM_PROMPT)

        scenes = [
            NewsScene(
                scene_id=s["scene_id"],
                narration=s["narration"],
                image_prompt=s["image_prompt"],
            )
            for s in result["scenes"]
        ]

        full_narration = "".join(s.narration for s in scenes)

        script = NewsScript(
            title=title,
            scenes=scenes,
            full_narration=full_narration,
            publish_title=result.get("publish_title", title[:20]),
            tags=result.get("tags", ["#国际新闻", "#突发", "#中东局势"]),
            word_count=len(full_narration),
        )

        log.info(f"News script generated: {len(scenes)} scenes, {script.word_count} chars")
        return script
