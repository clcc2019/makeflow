from __future__ import annotations

import asyncio

from publisher.base import BasePublisher, PublishRequest, PublishResult
from utils.logger import log


class BilibiliPublisher(BasePublisher):
    """Publish videos to Bilibili (B站) using Playwright browser automation."""

    PLATFORM_NAME = "bilibili"
    CREATOR_URL = "https://member.bilibili.com/platform/upload/video/frame"

    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        log.info(f"Bilibili: publishing '{request.title}'")

        await page.goto(self.CREATOR_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if "passport" in page.url.lower() or "login" in page.url.lower():
            log.error("Bilibili: not logged in")
            return PublishResult(platform=self.PLATFORM_NAME, success=False, error="Not logged in")

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(request.video_path)
        log.info("Bilibili: video uploaded, waiting for processing...")
        await asyncio.sleep(10)

        await page.wait_for_selector('.upload-success', timeout=300000)

        title_input = page.locator('input[maxlength="80"]').first
        await title_input.clear()
        await title_input.fill(request.title)

        tag_input = page.locator('[placeholder*="标签"]').first
        if await tag_input.is_visible():
            for tag in request.tags[:5]:
                tag_clean = tag.lstrip("#")
                await tag_input.fill(tag_clean)
                await asyncio.sleep(0.5)
                await tag_input.press("Enter")
                await asyncio.sleep(0.3)

        if request.cover_path:
            try:
                cover_btn = page.locator('text=更改封面').first
                await cover_btn.click()
                await asyncio.sleep(1)
                cover_input = page.locator('input[accept*="image"]')
                await cover_input.last.set_input_files(request.cover_path)
                await asyncio.sleep(2)
                confirm = page.locator('text=完成').first
                await confirm.click()
            except Exception as e:
                log.warning(f"Bilibili: cover upload failed: {e}")

        if request.aigc_label:
            try:
                aigc_checkbox = page.locator('text=AI生成').first
                if await aigc_checkbox.is_visible():
                    await aigc_checkbox.click()
            except Exception:
                pass

        publish_btn = page.locator('button:has-text("投稿")').first
        if not await publish_btn.is_visible():
            publish_btn = page.locator('button:has-text("立即投稿")').first
        await publish_btn.click()
        await asyncio.sleep(3)

        log.info("Bilibili: video published successfully")
        return PublishResult(platform=self.PLATFORM_NAME, success=True)
