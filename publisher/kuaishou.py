from __future__ import annotations

import asyncio

from publisher.base import BasePublisher, PublishRequest, PublishResult
from utils.logger import log


class KuaishouPublisher(BasePublisher):
    """Publish videos to Kuaishou (快手) using Playwright browser automation."""

    PLATFORM_NAME = "kuaishou"
    CREATOR_URL = "https://cp.kuaishou.com/article/publish/video"

    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        log.info(f"Kuaishou: publishing '{request.title}'")

        await page.goto(self.CREATOR_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if "passport" in page.url.lower():
            log.error("Kuaishou: not logged in")
            return PublishResult(platform=self.PLATFORM_NAME, success=False, error="Not logged in")

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(request.video_path)
        log.info("Kuaishou: video uploaded, waiting...")
        await asyncio.sleep(10)

        title_input = page.locator('[placeholder*="描述"]').first
        if not await title_input.is_visible():
            title_input = page.locator('textarea').first
        await title_input.click()
        await title_input.fill(request.title)

        for tag in request.tags[:5]:
            tag_text = tag if tag.startswith("#") else f"#{tag}"
            await title_input.type(f" {tag_text}", delay=30)
            await asyncio.sleep(0.3)

        if request.cover_path:
            try:
                cover_input = page.locator('input[accept*="image"]').first
                await cover_input.set_input_files(request.cover_path)
                await asyncio.sleep(2)
            except Exception as e:
                log.warning(f"Kuaishou: cover upload failed: {e}")

        publish_btn = page.locator('button:has-text("发布")').first
        await publish_btn.click()
        await asyncio.sleep(3)

        log.info("Kuaishou: video published successfully")
        return PublishResult(platform=self.PLATFORM_NAME, success=True)
