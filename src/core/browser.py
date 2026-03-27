"""Playwright browser lifecycle — launch Chrome with stealth, manage context."""

import shutil
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from src.core.logger import get_logger

logger = get_logger(__name__)


def find_chrome() -> str | None:
    """Check if system Chrome is available."""
    import platform
    import os

    system = platform.system()
    if system == "Darwin":
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(path):
            return path
    elif system == "Windows":
        for p in [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]:
            if os.path.exists(p):
                return p
    else:  # Linux
        for name in ["google-chrome", "google-chrome-stable"]:
            if shutil.which(name):
                return name

    return None


@asynccontextmanager
async def launch_browser(headless: bool = True, storage_state: str | None = None):
    """Launch Chrome with stealth and yield (context, page). Cleans up on exit."""
    import os

    if not find_chrome():
        raise RuntimeError(
            "未找到 Google Chrome。请安装 Chrome: https://www.google.com/chrome/\n"
            "ykt-cli 需要 Chrome 以支持 H.264 视频解码。"
        )

    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            channel="chrome",
        )
        logger.info("浏览器已启动 (headless=%s, channel=chrome)", headless)

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
            "is_mobile": False,
        }
        if storage_state and os.path.exists(storage_state):
            ctx_kwargs["storage_state"] = storage_state
            logger.info("从 storage_state 恢复登录态")

        context = await browser.new_context(**ctx_kwargs)
        context.set_default_timeout(30000)
        page = await context.new_page()
        try:
            yield context, page
        finally:
            await browser.close()
