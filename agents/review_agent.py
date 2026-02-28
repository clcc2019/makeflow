from __future__ import annotations

from utils.llm_client import get_llm
from utils.logger import log


class ReviewAgent:
    """Generates platform-specific titles and tags for multi-platform publishing."""

    SYSTEM_PROMPT = """你是一位精通多平台运营的短视频标题和标签优化师。
你需要针对不同平台的用户画像和算法偏好，生成差异化的标题和标签。"""

    PLATFORM_PROMPT = """请为以下短视频生成多平台发布方案：

视频标题：{title}
视频文案摘要：{summary}
通用标签：{tags}

请针对以下平台分别生成标题和标签：
1. 抖音（douyin）：标题简短有力，标签带#号
2. 快手（kuaishou）：接地气，口语化
3. B站（bilibili）：可以稍长，信息量大，年轻化
4. 小红书（xiaohongshu）：加emoji，种草风格
5. 视频号（weixin_video）：稳重专业，适合转发

以JSON格式返回：
{{
  "douyin": {{"title": "...", "tags": ["#标签1", "#标签2"]}},
  "kuaishou": {{"title": "...", "tags": ["#标签1", "#标签2"]}},
  "bilibili": {{"title": "...", "tags": ["标签1", "标签2"]}},
  "xiaohongshu": {{"title": "...", "tags": ["#标签1", "#标签2"]}},
  "weixin_video": {{"title": "...", "tags": ["#标签1", "#标签2"]}}
}}"""

    def __init__(self, llm_provider: str | None = None):
        self.llm = get_llm(llm_provider)

    def generate_platform_metadata(
        self, title: str, summary: str, tags: list[str]
    ) -> dict:
        prompt = self.PLATFORM_PROMPT.format(
            title=title,
            summary=summary[:200],
            tags=", ".join(tags),
        )
        try:
            result = self.llm.chat_json(prompt=prompt, system=self.SYSTEM_PROMPT)
            log.info(f"Platform metadata generated for: {title}")
            return result
        except Exception as e:
            log.warning(f"Platform metadata generation failed: {e}")
            default = {"title": title, "tags": tags}
            return {p: default for p in ["douyin", "kuaishou", "bilibili", "xiaohongshu", "weixin_video"]}
