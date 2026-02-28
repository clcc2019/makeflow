from __future__ import annotations

import asyncio
from typing import Type

from publisher.base import BasePublisher, PublishRequest, PublishResult
from publisher.douyin import DouyinPublisher
from publisher.kuaishou import KuaishouPublisher
from publisher.bilibili import BilibiliPublisher
from publisher.xiaohongshu import XiaohongshuPublisher
from publisher.weixin_video import WeixinVideoPublisher
from utils.config import get_settings
from utils.logger import log


PLATFORM_MAP: dict[str, Type[BasePublisher]] = {
    "douyin": DouyinPublisher,
    "kuaishou": KuaishouPublisher,
    "bilibili": BilibiliPublisher,
    "xiaohongshu": XiaohongshuPublisher,
    "weixin_video": WeixinVideoPublisher,
}


class PublishManager:
    """Manages publishing to multiple platforms with platform-specific metadata."""

    def __init__(self, headless: bool = True):
        self.settings = get_settings()
        self.headless = headless
        self.enabled_platforms = self.settings["publish"].get("platforms", [])
        self.aigc_label = self.settings["publish"].get("aigc_label", True)

    def publish_to_all(
        self,
        video_path: str,
        cover_path: str | None,
        platform_metadata: dict,
    ) -> list[PublishResult]:
        results = []
        for platform_name in self.enabled_platforms:
            if platform_name not in PLATFORM_MAP:
                log.warning(f"Unknown platform: {platform_name}, skipping")
                continue

            meta = platform_metadata.get(platform_name, {})
            title = meta.get("title", "")
            tags = meta.get("tags", [])

            if not title:
                log.warning(f"No title for {platform_name}, skipping")
                continue

            request = PublishRequest(
                video_path=video_path,
                title=title,
                tags=tags,
                cover_path=cover_path,
                aigc_label=self.aigc_label,
            )

            publisher_cls = PLATFORM_MAP[platform_name]
            publisher = publisher_cls(headless=self.headless)

            log.info(f"Publishing to {platform_name}: '{title}'")
            result = publisher.publish(request)
            results.append(result)

            if result.success:
                log.info(f"  {platform_name}: SUCCESS")
            else:
                log.error(f"  {platform_name}: FAILED - {result.error}")

        return results

    def publish_to_platform(
        self,
        platform_name: str,
        video_path: str,
        title: str,
        tags: list[str],
        cover_path: str | None = None,
    ) -> PublishResult:
        if platform_name not in PLATFORM_MAP:
            return PublishResult(platform=platform_name, success=False, error="Unknown platform")

        request = PublishRequest(
            video_path=video_path,
            title=title,
            tags=tags,
            cover_path=cover_path,
            aigc_label=self.aigc_label,
        )

        publisher = PLATFORM_MAP[platform_name](headless=self.headless)
        return publisher.publish(request)
