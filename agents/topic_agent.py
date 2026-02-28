from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime

import feedparser
import httpx

from utils.config import get_rss_config, get_settings
from utils.llm_client import get_llm
from utils.logger import log
from models.database import get_session, TopicHistory


@dataclass
class TopicCandidate:
    title: str
    summary: str = ""
    source: str = ""
    url: str = ""
    category: str = ""
    published: str = ""
    score: float = 0.0
    reasoning: str = ""


class TopicAgent:
    """Fetches trending AI/tech topics from RSS feeds and scores them with LLM."""

    SYSTEM_PROMPT = """你是一位资深的AI科技自媒体选题策划师。你的任务是评估候选选题的质量。

评估维度（每项1-10分）：
1. 科普价值：这个话题是否有科普意义？普通观众能学到什么？
2. 流量潜力：这个话题是否有吸引力？是否是热点？是否能引发好奇心？
3. 内容可行性：能否在60-90秒内讲清楚？是否适合口播形式？

只选择与AI、人工智能、科技创新、大模型、芯片、机器人、自动驾驶等相关的话题。
排除纯融资新闻、招聘信息、广告软文。"""

    SCORE_PROMPT_TEMPLATE = """请对以下候选选题进行评分。

候选选题列表：
{topics_text}

请以JSON格式返回评分结果，格式如下：
[
  {{
    "title": "选题标题",
    "score": 8.5,
    "reasoning": "评分理由（一句话）",
    "hook": "建议的视频开头悬念句（15字以内）"
  }}
]

只返回得分>=7分的选题，按分数从高到低排列。最多返回5个。"""

    def __init__(self, llm_provider: str | None = None):
        self.llm = get_llm(llm_provider)
        self.rss_config = get_rss_config()
        self.settings = get_settings()

    def fetch_rss_topics(self) -> list[TopicCandidate]:
        candidates = []
        keywords_inc = set(k.lower() for k in self.rss_config.get("keywords", {}).get("include", []))
        keywords_exc = set(k.lower() for k in self.rss_config.get("keywords", {}).get("exclude", []))

        for feed_cfg in self.rss_config.get("feeds", []):
            try:
                log.info(f"Fetching RSS: {feed_cfg['name']} ({feed_cfg['url']})")
                parsed = feedparser.parse(feed_cfg["url"])
                for entry in parsed.entries[:20]:
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()[:300]
                    text_lower = (title + " " + summary).lower()

                    if any(kw in text_lower for kw in keywords_exc):
                        continue
                    if not any(kw in text_lower for kw in keywords_inc):
                        continue

                    candidates.append(TopicCandidate(
                        title=title,
                        summary=summary,
                        source=feed_cfg["name"],
                        url=entry.get("link", ""),
                        category=feed_cfg.get("category", ""),
                        published=entry.get("published", ""),
                    ))
            except Exception as e:
                log.warning(f"Failed to fetch RSS {feed_cfg['name']}: {e}")

        log.info(f"Fetched {len(candidates)} candidate topics from RSS")
        return candidates

    def deduplicate(self, candidates: list[TopicCandidate]) -> list[TopicCandidate]:
        session = get_session()
        try:
            existing_titles = {
                row.title.lower()
                for row in session.query(TopicHistory.title).all()
            }
        finally:
            session.close()

        unique = []
        seen = set()
        for c in candidates:
            key = hashlib.md5(c.title.lower().encode()).hexdigest()
            if key not in seen and c.title.lower() not in existing_titles:
                seen.add(key)
                unique.append(c)

        log.info(f"After dedup: {len(unique)} unique topics (from {len(candidates)})")
        return unique

    def score_topics(self, candidates: list[TopicCandidate]) -> list[TopicCandidate]:
        if not candidates:
            return []

        topics_text = "\n".join(
            f"{i+1}. [{c.source}] {c.title}\n   摘要: {c.summary[:150]}"
            for i, c in enumerate(candidates[:30])
        )

        prompt = self.SCORE_PROMPT_TEMPLATE.format(topics_text=topics_text)

        try:
            results = self.llm.chat_json(prompt=prompt, system=self.SYSTEM_PROMPT)
        except Exception as e:
            log.error(f"LLM scoring failed: {e}")
            return candidates[:5]

        title_to_candidate = {c.title: c for c in candidates}
        scored = []
        for item in results:
            title = item.get("title", "")
            if title in title_to_candidate:
                c = title_to_candidate[title]
                c.score = float(item.get("score", 0))
                c.reasoning = item.get("reasoning", "")
                scored.append(c)

        scored.sort(key=lambda x: x.score, reverse=True)
        log.info(f"Scored {len(scored)} topics, top: {scored[0].title if scored else 'none'}")
        return scored

    def save_to_history(self, topics: list[TopicCandidate], selected_count: int = 3):
        session = get_session()
        try:
            for i, t in enumerate(topics):
                session.add(TopicHistory(
                    title=t.title,
                    source=t.source,
                    url=t.url,
                    score=t.score,
                    selected=1 if i < selected_count else 0,
                ))
            session.commit()
        finally:
            session.close()

    def run(self, count: int = 3) -> list[TopicCandidate]:
        """Full pipeline: fetch -> dedup -> score -> select top N."""
        log.info(f"=== Topic Agent: selecting {count} topics ===")
        candidates = self.fetch_rss_topics()
        if not candidates:
            log.warning("No candidates fetched, using fallback topics")
            return self._fallback_topics(count)

        unique = self.deduplicate(candidates)
        if not unique:
            log.warning("All topics already covered, using fallback")
            return self._fallback_topics(count)

        scored = self.score_topics(unique)
        selected = scored[:count]

        self.save_to_history(scored, selected_count=count)
        log.info(f"Selected {len(selected)} topics: {[t.title for t in selected]}")
        return selected

    def _fallback_topics(self, count: int) -> list[TopicCandidate]:
        """Generate evergreen AI/tech topics when RSS fails."""
        prompt = f"""请生成{count}个适合短视频科普的AI/科技话题。

要求：
- 话题新颖、有趣、有科普价值
- 适合60-90秒口播讲解
- 面向普通观众，通俗易懂

以JSON格式返回：
[
  {{"title": "话题标题", "summary": "一句话描述", "score": 8.5}}
]"""
        try:
            results = self.llm.chat_json(prompt=prompt, system=self.SYSTEM_PROMPT)
            return [
                TopicCandidate(
                    title=item["title"],
                    summary=item.get("summary", ""),
                    source="llm_generated",
                    score=item.get("score", 8.0),
                )
                for item in results[:count]
            ]
        except Exception as e:
            log.error(f"Fallback topic generation failed: {e}")
            return [TopicCandidate(
                title="AI Agent是什么？为什么2025年是AI Agent元年",
                summary="解释AI Agent的概念和应用场景",
                source="default",
                score=8.0,
            )]
