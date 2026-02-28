from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from utils.logger import log


@dataclass
class PublishRequest:
    video_path: str
    title: str
    tags: list[str]
    cover_path: str | None = None
    aigc_label: bool = True
    schedule_time: str | None = None


@dataclass
class PublishResult:
    platform: str
    success: bool
    url: str = ""
    error: str = ""


class BasePublisher(ABC):
    """Base class for platform-specific video publishers using Playwright."""

    PLATFORM_NAME: str = ""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.cookie_dir = Path("./data/cookies")
        self.cookie_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cookie_path(self) -> Path:
        return self.cookie_dir / f"{self.PLATFORM_NAME}.json"

    async def _get_browser_context(self):
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=self.headless)

        if self.cookie_path.exists():
            context = await browser.new_context(storage_state=str(self.cookie_path))
            log.info(f"{self.PLATFORM_NAME}: loaded saved cookies")
        else:
            context = await browser.new_context()
            log.info(f"{self.PLATFORM_NAME}: no saved cookies, may need login")

        return pw, browser, context

    async def _save_cookies(self, context):
        await context.storage_state(path=str(self.cookie_path))
        log.info(f"{self.PLATFORM_NAME}: cookies saved")

    @abstractmethod
    async def _publish(self, context, page, request: PublishRequest) -> PublishResult:
        ...

    async def publish_async(self, request: PublishRequest) -> PublishResult:
        pw, browser, context = await self._get_browser_context()
        try:
            page = await context.new_page()
            result = await self._publish(context, page, request)
            await self._save_cookies(context)
            return result
        except Exception as e:
            log.error(f"{self.PLATFORM_NAME} publish failed: {e}")
            return PublishResult(
                platform=self.PLATFORM_NAME,
                success=False,
                error=str(e),
            )
        finally:
            await browser.close()
            await pw.stop()

    def publish(self, request: PublishRequest) -> PublishResult:
        return asyncio.run(self.publish_async(request))
