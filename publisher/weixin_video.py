from __future__ import annotations

import asyncio

from publisher.base import BasePublisher, PublishRequest, PublishResult
from utils.logger import log


class WeixinVideoPublisher(BasePublisher):
    """Publish videos to Weixin Channels (视频号) using Playwright browser automation."""

    PLATFORM_NAME = "weixin_video"
    CREATOR_URL = "https://channels.weixin.qq.com/platform/post/create"

    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        log.info(f"WeixinVideo: publishing '{request.title}'")

        await page.goto(self.CREATOR_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if "login" in page.url.lower() or await page.locator('text=请使用微信扫码').is_visible():
            log.error("WeixinVideo: not logged in, QR code scan required")
            return PublishResult(platform=self.PLATFORM_NAME, success=False, error="Not logged in")

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(request.video_path)
        log.info("WeixinVideo: video uploaded")
        await asyncio.sleep(10)

        desc_area = page.locator('[contenteditable="true"]').first
        if not await desc_area.is_visible():
            desc_area = page.locator('textarea').first
        await desc_area.click()

        full_text = request.title
        for tag in request.tags[:5]:
            tag_text = tag if tag.startswith("#") else f"#{tag}"
            full_text += f" {tag_text}"
        await desc_area.type(full_text, delay=30)

        if request.aigc_label:
            try:
                aigc = page.locator('text=AI生成').first
                if await aigc.is_visible():
                    await aigc.click()
            except Exception:
                pass

        publish_btn = page.locator('button:has-text("发表")').first
        await publish_btn.click()
        await asyncio.sleep(3)

        log.info("WeixinVideo: video published successfully")
        return PublishResult(platform=self.PLATFORM_NAME, success=True)
