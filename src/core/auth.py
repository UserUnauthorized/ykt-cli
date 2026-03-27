"""WeChat QR login, session restore, and state persistence for YuKeTang."""

import asyncio
import json
import os
import re
from pathlib import Path

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.core.logger import get_logger
from src import ui

logger = get_logger(__name__)


async def _extract_and_print_qr(page: Page, inner_frame) -> str | None:
    import qrcode as qrcode_lib

    qr_img = inner_frame.locator("img.js_qrcode_img").first
    await qr_img.wait_for(timeout=15_000, state="attached")
    src = await qr_img.get_attribute("src")
    if not src:
        return None

    match = re.search(r"/connect/qrcode/(\w+)", src)
    if not match:
        return None

    uuid = match.group(1)
    logger.info("二维码已提取 (uuid=%s...)", uuid[:8])
    qr_url = f"https://open.weixin.qq.com/connect/confirm?uuid={uuid}"

    qr = qrcode_lib.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)

    ui.console.print()
    ui.info("请用微信扫描以下二维码登录:")
    ui.console.print()
    qr.print_ascii(invert=True)
    ui.console.print()
    return uuid


async def _qr_watch_loop(page: Page) -> None:
    try:
        import qrcode as _  # noqa: F401

        await page.wait_for_timeout(3000)
        inner_frame = page.frame_locator("#qrcode-box iframe").frame_locator("iframe")
        await _extract_and_print_qr(page, inner_frame)

        while True:
            await asyncio.sleep(240)
            ui.warn("二维码即将过期，正在刷新...")
            logger.info("刷新二维码 (4分钟周期)")
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            inner_frame = page.frame_locator("#qrcode-box iframe").frame_locator("iframe")
            await _extract_and_print_qr(page, inner_frame)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception("终端二维码处理失败")
        ui.warn(f"终端二维码处理失败: {e}")


async def wait_for_login(page: Page, url: str, headless: bool = True, check_tab: str = "学习内容") -> None:
    """Navigate to URL and wait for user to complete WeChat QR login."""
    if headless:
        await page.context.route("**localhost.weixin.qq.com**", lambda route: route.abort())
        logger.debug("已屏蔽 localhost.weixin.qq.com")

    await page.goto(url, wait_until="domcontentloaded")
    # 等待 JS 执行：若会话过期，SPA 会在此期间完成客户端重定向到登录页
    await page.wait_for_timeout(3000)
    logger.info("已导航到登录页")

    qr_task = None
    if headless:
        qr_task = asyncio.create_task(_qr_watch_loop(page))
    else:
        ui.info("请在浏览器中扫码登录...")

    try:
        await page.get_by_role("tab", name=check_tab).wait_for(timeout=600_000)
    except (TimeoutError, PlaywrightTimeoutError):
        logger.error("登录超时 (10分钟)")
        ui.error("登录超时（10 分钟），请重新运行")
        raise SystemExit(1)

    if qr_task:
        qr_task.cancel()
        try:
            await qr_task
        except asyncio.CancelledError:
            pass

    if headless:
        await page.context.unroute_all()

    logger.info("登录成功")
    ui.success("登录成功！")


async def try_restore_login(page: Page, url: str, check_tab: str = "学习内容") -> bool:
    """Try to restore a previous session. Returns True if login is still valid."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # 等 load 事件确保 JS 已加载执行（含会话校验和可能的重定向）
        await page.wait_for_load_state("load", timeout=30_000)
        await page.get_by_role("tab", name=check_tab).wait_for(timeout=10_000)
        logger.info("登录态恢复成功")
        return True
    except (TimeoutError, Exception) as e:
        logger.info("登录态恢复失败: %s", e)
        return False


async def ensure_logged_in_for_slide(page: Page, headless: bool = True) -> None:
    """Login flow for slide download — checks by page title instead of tab."""
    LOGIN_URL = "https://www.yuketang.cn/web"

    if headless:
        await page.context.route("**localhost.weixin.qq.com**", lambda route: route.abort())

    await page.goto(LOGIN_URL, wait_until="networkidle")

    if "/web/?next=" not in page.url and "登录" not in await page.title():
        ui.success("已登录，无需重新认证")
        if headless:
            await page.context.unroute_all()
        return

    ui.info("需要登录")

    qr_task = None
    if headless:
        qr_task = asyncio.create_task(_qr_watch_loop(page))
    else:
        ui.info("请在浏览器中扫码登录...")

    try:
        await page.wait_for_function(
            "() => !document.title.includes('登录')",
            timeout=600_000,
        )
    except Exception:
        ui.error("登录超时（10 分钟），请重新运行")
        raise SystemExit(1)
    finally:
        if qr_task:
            qr_task.cancel()
            try:
                await qr_task
            except asyncio.CancelledError:
                pass
        if headless:
            await page.context.unroute_all()

    ui.success("登录成功")


async def save_browser_state(context, path: str) -> None:
    """Export browser context state to file with restricted permissions."""
    state = await context.storage_state()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))
    os.chmod(path, 0o600)
    logger.info("浏览器状态已保存")
