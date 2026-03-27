"""ykt login — WeChat QR login."""

import asyncio
import typer

from src.core.browser import launch_browser
from src.core.auth import wait_for_login, save_browser_state
from src.core.profile import get_state_path, has_state, create_profile, load_profile
from src.core.config import load_config
from src.core.logger import setup_logging
from src.run.course import INDEX_URL
from src import ui


def login(
    ctx: typer.Context,
    profile: str = typer.Option(None, help="使用指定账号"),
    headful: bool = typer.Option(False, help="显示浏览器窗口"),
):
    """扫码登录雨课堂"""
    debug = ctx.obj.get("debug", False)
    asyncio.run(_login(profile, headful, debug))


async def _login(profile_name: str | None, headful: bool, debug: bool):
    cfg = await load_config()
    setup_logging(debug=debug, log_level=cfg.log_level, retention_days=cfg.retention_days)
    ui.banner()

    profile_name = profile_name or "default"
    if not load_profile(profile_name):
        create_profile(profile_name)
        ui.success(f"已创建账号: {profile_name}")

    state_path = str(get_state_path(profile_name))
    storage = state_path if has_state(profile_name) else None

    async with launch_browser(headless=not headful, storage_state=storage) as (context, page):
        await wait_for_login(page, INDEX_URL, headless=not headful, check_tab="我听的课")
        await save_browser_state(context, state_path)
        ui.success(f"登录状态已保存到账号: {profile_name}")
