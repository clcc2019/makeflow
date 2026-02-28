from __future__ import annotations

import asyncio

from publisher.base import BasePublisher, PublishRequest, PublishResult
from utils.logger import log


class DouyinPublisher(BasePublisher):
    """Publish videos to Douyin (抖音) using Playwright browser automation."""

    PLATFORM_NAME = "douyin"
    CREATOR_URL = "https://creator.douyin.com/creator-micro/content/upload"

    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        log.info(f"Douyin: publishing '{request.title}'")

        await page.goto(self.CREATOR_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if "login" in page.url.lower():
            log.error("Douyin: not logged in. Please login manually and save cookies first.")
            return PublishResult(platform=self.PLATFORM_NAME, success=False, error="Not logged in")

        # Upload video file
        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(request.video_path)
        log.info("Douyin: video file uploaded, waiting for processing...")
        await asyncio.sleep(5)

        # Wait for upload to complete
        await page.wait_for_selector('text=重新上传', timeout=120000)
        log.info("Douyin: upload complete")

        # Fill title
        title_input = page.locator('[data-placeholder="添加作品描述"]').first
        await title_input.click()
        await title_input.fill("")
        await title_input.type(request.title, delay=50)
        await asyncio.sleep(1)

        # Add tags
        for tag in request.tags[:5]:
            tag_text = tag if tag.startswith("#") else f"#{tag}"
            await title_input.type(f" {tag_text}", delay=30)
            await asyncio.sleep(0.5)

        # Upload cover if available
        if request.cover_path:
            try:
                cover_btn = page.locator('text=选择封面').first
                await cover_btn.click()
                await asyncio.sleep(1)
                upload_cover = page.locator('text=上传封面').first
                await upload_cover.click()
                cover_input = page.locator('input[accept*="image"]').first
                await cover_input.set_input_files(request.cover_path)
                await asyncio.sleep(2)
                confirm_btn = page.locator('text=完成').first
                await confirm_btn.click()
                await asyncio.sleep(1)
            except Exception as e:
                log.warning(f"Douyin: cover upload failed, skipping: {e}")

        # Set AIGC label if required
        if request.aigc_label:
            try:
                aigc_option = page.locator('text=AI生成').first
                if await aigc_option.is_visible():
                    await aigc_option.click()
                    await asyncio.sleep(0.5)
            except Exception:
                log.warning("Douyin: AIGC label not found, skipping")

        # Submit
        publish_btn = page.locator('button:has-text("发布")').first
        await publish_btn.click()
        await asyncio.sleep(3)

        log.info("Douyin: video published successfully")
        return PublishResult(platform=self.PLATFORM_NAME, success=True)
