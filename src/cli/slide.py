"""ykt slide — download course slides as PDF."""

import asyncio
from pathlib import Path
from typing import Optional

import typer

from src.core.browser import launch_browser
from src.core.auth import (
    ensure_logged_in_for_slide,
    save_browser_state,
    wait_for_login,
    try_restore_login,
)
from src.core.profile import (
    get_state_path,
    has_state,
    load_profile,
    create_profile,
    list_profiles,
    load_index,
)
from src.core.config import load_config
from src.core.logger import setup_logging
from src.slide.downloader import download_lesson_slides, download_slides_api
from src import ui


def _collect_urls(urls: list[str], file: str | None) -> list[str]:
    result = list(urls)
    if file:
        path = Path(file)
        if not path.exists():
            ui.error(f"文件不存在: {path}")
            raise typer.Exit(1)
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                result.append(line)
    return result


def slide(
    ctx: typer.Context,
    urls: Optional[list[str]] = typer.Argument(None, help="课件报告 URL"),
    file: Optional[str] = typer.Option(None, "-f", "--file", help="从文件读取 URL"),
    output: str = typer.Option("output", "-o", "--output", help="输出目录"),
    profile: Optional[str] = typer.Option(None, help="使用指定账号"),
    headful: bool = typer.Option(False, help="显示浏览器窗口"),
):
    """下载雨课堂课件 PDF"""
    debug = ctx.obj.get("debug", False)
    all_urls = _collect_urls(urls or [], file)
    if all_urls:
        asyncio.run(_slide_urls(all_urls, output, profile, headful, debug))
    else:
        asyncio.run(_slide_interactive(output, profile, headful, debug))


async def _slide_urls(urls, output_dir, profile_name, headful, debug):
    cfg = await load_config()
    setup_logging(debug=debug, log_level=cfg.log_level, retention_days=cfg.retention_days)
    ui.banner()

    profile_name = profile_name or "default"
    if not load_profile(profile_name):
        create_profile(profile_name)

    state_path = str(get_state_path(profile_name))
    storage = state_path if has_state(profile_name) else None

    ui.info(f"待下载: {len(urls)} 个课件报告")

    async with launch_browser(headless=not headful, storage_state=storage) as (context, page):
        ui.info("检查登录状态...")
        await ensure_logged_in_for_slide(page, headless=not headful)
        await save_browser_state(context, state_path)

        output_path = Path(output_dir)
        all_saved: list[Path] = []

        for i, url in enumerate(urls):
            ui.section(f"[{i+1}/{len(urls)}]")
            try:
                saved = await download_lesson_slides(page, url, output_path)
                all_saved.extend(saved)
            except Exception as e:
                ui.error(f"下载失败: {type(e).__name__}: {e}")

        ui.console.print()
        ui.success(f"全部完成，共下载 {len(all_saved)} 个文件")


async def _slide_interactive(output_dir, profile_name, headful, debug):
    import httpx
    from src.run.course import group_by_term, INDEX_URL
    from src.slide.api import (
        fetch_courses,
        fetch_lessons,
        fetch_presentations,
        build_cookies,
        format_lesson_date,
    )

    cfg = await load_config()
    setup_logging(debug=debug, log_level=cfg.log_level, retention_days=cfg.retention_days)
    ui.banner()

    # 1. Resolve profile (same pattern as src/cli/run.py)
    if not profile_name:
        profiles = list_profiles()
        if profiles:
            index = load_index()
            profile_name = ui.profile_menu(profiles, index["default"])
        if profile_name is None:
            name = ui.prompt_new_profile()
            create_profile(name)
            profile_name = name

    profile_name = profile_name or "default"
    if not load_profile(profile_name):
        create_profile(profile_name)

    ui.profile_info(profile_name)
    state_path = str(get_state_path(profile_name))
    storage = state_path if has_state(profile_name) else None
    headless = not headful

    async with launch_browser(headless=headless, storage_state=storage) as (context, page):
        # 2. Login
        restored = False
        if storage:
            ui.info("正在恢复登录态...")
            restored = await try_restore_login(page, INDEX_URL, check_tab="我听的课")
            if restored:
                ui.success("登录态有效")
            else:
                ui.warn("登录态已过期，需要重新扫码")

        if not restored:
            await wait_for_login(page, INDEX_URL, headless=headless, check_tab="我听的课")

        await save_browser_state(context, state_path)

        # 3. Extract cookies for httpx
        raw_cookies = await context.cookies()
        cookies = build_cookies(raw_cookies)

        async with httpx.AsyncClient(cookies=cookies, timeout=30.0) as client:
            # 4. Select course
            ui.info("正在获取课程列表...")
            courses = await fetch_courses(client)
            if not courses:
                ui.error("获取课程列表失败")
                return

            grouped = group_by_term(courses)
            term = ui.term_menu(grouped)
            selected_course = ui.course_menu(grouped[term])
            classroom_id = selected_course["classroom_id"]
            ui.info(f"已选择: {selected_course['course']['name']}")

            # 5. Fetch and select lessons
            ui.info("正在获取课时列表...")
            lessons = await fetch_lessons(client, classroom_id)
            if not lessons:
                ui.error("该课程暂无课堂记录")
                return

            menu_items = [
                {"title": l.title, "date": format_lesson_date(l.create_time)}
                for l in lessons
            ]
            selected_indices = await ui.lesson_checkbox_menu(menu_items)
            if not selected_indices:
                return

            selected_lessons = [lessons[i] for i in selected_indices]

            # 6. Download
            output_path = Path(output_dir)
            all_saved: list[Path] = []

            for i, lesson in enumerate(selected_lessons):
                ui.section(f"[{i+1}/{len(selected_lessons)}] {lesson.title}")
                try:
                    presentations = await fetch_presentations(client, lesson.courseware_id)
                    if not presentations:
                        ui.warn("该课时无课件")
                        continue
                    saved = await download_slides_api(
                        lesson.courseware_id,
                        lesson.title,
                        presentations,
                        output_path,
                    )
                    all_saved.extend(saved)
                except Exception as e:
                    ui.error(f"下载失败: {type(e).__name__}: {e}")

            ui.console.print()
            ui.success(f"全部完成，共下载 {len(all_saved)} 个文件")
