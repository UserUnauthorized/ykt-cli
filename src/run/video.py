"""Video playback control — load, play, speed hack, progress monitoring."""

import asyncio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from src.core.logger import get_logger
from src import ui

logger = get_logger(__name__)


async def wait_for_video_load(page: Page, max_retries: int = 5) -> bool:
    for attempt in range(max_retries):
        try:
            await page.wait_for_function(
                "() => { const v = document.querySelector('video'); return v && v.duration > 0; }",
                timeout=10_000,
            )
        except (TimeoutError, PlaywrightTimeoutError):
            pass
        progress = await get_progress(page)
        duration = progress.get("duration", 0) if progress else 0
        if duration and duration > 0:
            logger.info("视频加载成功 (时长: %.0fs)", duration)
            ui.success(f"视频加载成功 (时长: {duration:.0f}s)")
            return True

        if attempt < max_retries - 1:
            wait_sec = 2 ** (attempt + 1)
            ui.warn(f"视频未加载，{wait_sec}s 后刷新... ({attempt+1}/{max_retries})")
            await asyncio.sleep(wait_sec)
            await page.reload()
        else:
            ui.error(f"视频加载失败，已重试 {max_retries} 次")
    return False


async def start_video(page: Page, speed: int = 2) -> None:
    if not await wait_for_video_load(page):
        raise RuntimeError("视频多次刷新后仍无法加载")

    # JS play() bypasses overlay elements (loading spinner, quiz mask) that
    # block Playwright's click actionability checks.
    await page.evaluate("document.querySelector('video')?.play()")
    try:
        await page.wait_for_function(
            "() => { const v = document.querySelector('video'); return v && !v.paused; }",
            timeout=5000,
        )
    except (TimeoutError, PlaywrightTimeoutError):
        ui.warn("视频未自动播放，继续设置倍速...")

    await page.evaluate("""(speed) => {
        const v = document.querySelector('video');
        const proto = HTMLMediaElement.prototype;
        const ratePD = Object.getOwnPropertyDescriptor(proto, 'playbackRate');
        const volPD = Object.getOwnPropertyDescriptor(proto, 'volume');
        ratePD.set.call(v, speed);
        volPD.set.call(v, 0);
        Object.defineProperty(v, 'playbackRate', {
            get() { return 1; }, set(val) { }, configurable: true
        });
        Object.defineProperty(v, 'volume', {
            get() { return 0; }, set(val) { }, configurable: true
        });
    }""", speed)
    logger.info("视频开始播放 (倍速: %dx)", speed)
    ui.success(f"已设置 {speed}x 倍速 + 静音")


async def get_progress(page: Page) -> dict:
    result = await page.evaluate("""() => {
        const video = document.querySelector('video');
        if (!video) return null;
        const proto = HTMLMediaElement.prototype;
        const ratePD = Object.getOwnPropertyDescriptor(proto, 'playbackRate');
        return {
            currentTime: video.currentTime,
            duration: video.duration,
            paused: video.paused,
            ended: video.ended,
            playbackRate: ratePD ? ratePD.get.call(video) : video.playbackRate
        };
    }""")
    return result or {}


async def get_completion(page: Page) -> str:
    el = page.locator("text=/完成度：\\d+%/").first
    if await el.count() > 0:
        return await el.inner_text()
    return ""


async def is_video_finished(page: Page) -> bool:
    progress = await get_progress(page)
    if not progress:
        return False
    if progress.get("ended"):
        return True
    duration = progress.get("duration", 0)
    current = progress.get("currentTime", 0)
    if duration > 0 and current >= duration - 2:
        return True
    return False
