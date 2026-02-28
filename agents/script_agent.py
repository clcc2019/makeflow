from __future__ import annotations

from dataclasses import dataclass

from agents.topic_agent import TopicCandidate
from utils.llm_client import get_llm
from utils.config import get_settings
from utils.logger import log


@dataclass
class VideoScript:
    title: str
    hook: str
    body: str
    full_script: str
    word_count: int
    publish_title: str
    tags: list[str]
    topic: TopicCandidate | None = None


class ScriptAgent:
    """Generates spoken-word scripts for AI/tech knowledge videos."""

    SYSTEM_PROMPT = """你是一位专业的AI科技短视频文案撰稿人。你的视频面向普通观众，风格特点：
- 语言口语化、生动有趣，像朋友聊天一样
- 善用类比和生活化的例子来解释复杂概念
- 节奏紧凑，信息密度高但不晦涩
- 有观点、有态度，不是干巴巴的百科读物

你写的文案将直接用于口播（TTS朗读），所以：
- 不要用括号、引号等书面符号
- 不要用"首先、其次、最后"这种书面过渡
- 多用短句，避免长从句
- 适当加入语气词让语感自然"""

    SCRIPT_PROMPT_TEMPLATE = """请为以下选题撰写一篇短视频口播文案：

选题：{title}
背景信息：{summary}

要求：
1. 总字数控制在{word_min}-{word_max}字之间（对应{dur_min}-{dur_max}秒的口播时长）
2. 文案结构：
   - 开头Hook（前3秒必须抓住注意力，用悬念、反问或惊人事实）
   - 核心知识点讲解（用一个核心类比或案例说明白）
   - 收尾（总结+引导互动，如"你觉得呢？评论区聊聊"）
3. 口播风格，不要有任何书面标记
4. 全程使用中文

请以JSON格式返回：
{{
  "hook": "开头前3秒的悬念句",
  "body": "正文完整口播文案（包含hook和结尾，连贯的一段话）",
  "publish_title": "视频发布标题（20字以内，有吸引力）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}}"""

    def __init__(self, llm_provider: str | None = None):
        self.llm = get_llm(llm_provider)
        self.settings = get_settings()

    def generate_script(self, topic: TopicCandidate) -> VideoScript:
        content_cfg = self.settings["content"]
        prompt = self.SCRIPT_PROMPT_TEMPLATE.format(
            title=topic.title,
            summary=topic.summary or "无额外背景信息",
            word_min=content_cfg["word_count_min"],
            word_max=content_cfg["word_count_max"],
            dur_min=content_cfg["video_duration_min"],
            dur_max=content_cfg["video_duration_max"],
        )

        log.info(f"Generating script for: {topic.title}")
        result = self.llm.chat_json(prompt=prompt, system=self.SYSTEM_PROMPT)

        body = result["body"]
        word_count = len(body)
        log.info(f"Script generated: {word_count} chars for '{topic.title}'")

        return VideoScript(
            title=topic.title,
            hook=result.get("hook", ""),
            body=body,
            full_script=body,
            word_count=word_count,
            publish_title=result.get("publish_title", topic.title[:20]),
            tags=result.get("tags", ["AI", "科技", "科普"]),
            topic=topic,
        )

    def review_script(self, script: VideoScript) -> VideoScript:
        """Review and optionally polish the script."""
        review_prompt = f"""请审核以下短视频口播文案，检查并修正以下问题：

文案内容：
{script.full_script}

审核要点：
1. 是否有事实错误或过度夸张的表述
2. 是否有不适合口播的书面化表达（括号、引号、列表符号等）
3. 字数是否在{self.settings['content']['word_count_min']}-{self.settings['content']['word_count_max']}之间
4. 开头前3秒是否足够吸引人
5. 是否有敏感词或可能导致平台审核不通过的内容

如果文案质量良好无需修改，返回：
{{"approved": true, "body": "原文案不变"}}

如果需要修改，返回：
{{"approved": false, "body": "修改后的完整文案", "changes": "修改说明"}}"""

        try:
            result = self.llm.chat_json(prompt=review_prompt, system="你是一位严格的短视频内容审核编辑。")

            if not result.get("approved", True):
                log.info(f"Script revised: {result.get('changes', 'minor edits')}")
                script.full_script = result["body"]
                script.body = result["body"]
                script.word_count = len(result["body"])

            return script
        except Exception as e:
            log.warning(f"Script review failed, using original: {e}")
            return script

    def run(self, topic: TopicCandidate) -> VideoScript:
        """Generate and review a script for the given topic."""
        script = self.generate_script(topic)
        script = self.review_script(script)
        log.info(f"Final script: '{script.publish_title}' ({script.word_count} chars)")
        return script
