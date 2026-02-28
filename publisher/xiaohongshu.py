from __future__ import annotations

import asyncio

from publisher.base import BasePublisher, PublishRequest, PublishResult
from utils.logger import log


class XiaohongshuPublisher(BasePublisher):
    """Publish videos to Xiaohongshu (小红书) using Playwright browser automation."""

    PLATFORM_NAME = "xiaohongshu"
    CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"

    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        log.info(f"Xiaohongshu: publishing '{request.title}'")

        await page.goto(self.CREATOR_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if "login" in page.url.lower():
            log.error("Xiaohongshu: not logged in")
            return PublishResult(platform=self.PLATFORM_NAME, success=False, error="Not logged in")

        # Switch to video tab
        video_tab = page.locator('text=上传视频').first
        if await video_tab.is_visible():
            await video_tab.click()
            await asyncio.sleep(1)

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(request.video_path)
        log.info("Xiaohongshu: video uploaded")
        await asyncio.sleep(10)

        title_input = page.locator('input[placeholder*="标题"]').first
        if not await title_input.is_visible():
            title_input = page.locator('[name="title"]').first
        await title_input.fill(request.title)

        desc_input = page.locator('[placeholder*="描述"]').first
        if await desc_input.is_visible():
            tags_text = " ".join(request.tags[:5])
            await desc_input.fill(tags_text)

        if request.aigc_label:
            try:
                aigc = page.locator('text=AI生成').first
                if await aigc.is_visible():
                    await aigc.click()
            except Exception:
                pass

        publish_btn = page.locator('button:has-text("发布")').first
        await publish_btn.click()
        await asyncio.sleep(3)

        log.info("Xiaohongshu: video published successfully")
        return PublishResult(platform=self.PLATFORM_NAME, success=True)
