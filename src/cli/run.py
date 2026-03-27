"""ykt run — auto course completion."""

import asyncio
import sys
import typer
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.core.browser import launch_browser
from src.core.auth import wait_for_login, try_restore_login, save_browser_state
from src.core.config import load_config
from src.core.profile import get_state_path, has_state, load_profile, create_profile, list_profiles, load_index
from src.core.logger import setup_logging, get_logger
from src.run.course import fetch_courses, group_by_term, build_course_url, INDEX_URL
from src.run.navigator import go_to_course_content, parse_units, is_completed, detect_content_type
from src.run.video import start_video, get_progress, is_video_finished, get_completion
from src.run.quiz import detect_quiz, handle_quiz
from src import ui


async def handle_graph(page) -> None:
    ui.info("图文内容，等待 5 秒...")
    await asyncio.sleep(5)
    ui.success("图文阅读完成")


async def handle_video_unit(page, speed: int, model: str, api_key: str, base_url: str) -> None:
    logger = get_logger("run")

    while await detect_quiz(page):
        await handle_quiz(page, model, api_key, base_url)
        await asyncio.sleep(1)

    await start_video(page, speed)

    logged_milestones = set()
    try:
        while True:
            if await detect_quiz(page):
                ui.video_progress_stop()
                await handle_quiz(page, model, api_key, base_url)
                await asyncio.sleep(1)
                continue

            if await is_video_finished(page):
                progress = await get_progress(page)
                comp = await get_completion(page)
                if progress:
                    dur = progress.get("duration", 0)
                    ui.video_progress(dur, dur, speed, comp, False)
                ui.video_progress_stop()
                ui.success(f"视频播放完成 {comp}")
                break

            progress = await get_progress(page)
            if progress:
                ct = progress.get("currentTime", 0)
                dur = progress.get("duration", 0)
                paused = progress.get("paused", False)
                comp = await get_completion(page)
                ui.video_progress(ct, dur, speed, comp, paused)

                if dur > 0:
                    pct = int(ct / dur * 100)
                    milestone = pct // 25 * 25
                    if milestone > 0 and milestone not in logged_milestones:
                        logged_milestones.add(milestone)
                        logger.info("视频进度 %d%% (%.0f/%.0fs) %s", milestone, ct, dur, comp)

                if paused and not await detect_quiz(page):
                    await page.evaluate("document.querySelector('video')?.play()")

            await asyncio.sleep(0.5)
    finally:
        ui.video_progress_stop()


def run(
    ctx: typer.Context,
    course_url: str = typer.Option(None, help="直接指定课程 URL"),
    profile: str = typer.Option(None, help="使用指定账号"),
    speed: int = typer.Option(None, help="视频倍速 (1-16)"),
    headful: bool = typer.Option(False, help="显示浏览器窗口"),
):
    """自动刷课（视频播放 + AI答题）"""
    debug = ctx.obj.get("debug", False)
    asyncio.run(_run(course_url, profile, speed, headful, debug))


async def _run(course_url, profile_name, speed_override, headful, debug):
    cfg = await load_config()
    setup_logging(debug=debug, log_level=cfg.log_level, retention_days=cfg.retention_days)
    logger = get_logger("run")

    ui.banner()

    # Resolve profile
    if not profile_name:
        profiles = list_profiles()
        if profiles:
            index = load_index()
            profile_name = ui.profile_menu(profiles, index["default"])
        if profile_name is None:
            name = ui.prompt_new_profile()
            create_profile(name)
            profile_name = name

    if not load_profile(profile_name):
        ui.error(f"账号 '{profile_name}' 不存在")
        sys.exit(1)

    # Resolve config
    api_key = cfg.openai.get("api_key", "")
    base_url = cfg.openai.get("base_url", "https://api.openai.com/v1")
    model = cfg.openai.get("model", "gpt-4o")
    speed = speed_override or cfg.video.get("speed", 2)

    if not api_key:
        ui.error("请在 ~/.ykt-cli/config.yaml 中设置 openai.api_key")
        sys.exit(1)

    ui.profile_info(profile_name)
    state_path = str(get_state_path(profile_name))
    storage = state_path if has_state(profile_name) else None
    headless = not headful

    async with launch_browser(headless=headless, storage_state=storage) as (context, page):
        try:
            login_url = course_url or INDEX_URL
            check_tab = "学习内容" if course_url else "我听的课"

            restored = False
            if storage:
                ui.info("正在恢复登录态...")
                restored = await try_restore_login(page, login_url, check_tab=check_tab)
                if restored:
                    ui.success("登录态有效，跳过扫码")
                else:
                    ui.warn("登录态已过期，需要重新扫码")

            if not restored:
                await wait_for_login(page, login_url, headless=headless, check_tab=check_tab)
                await save_browser_state(context, state_path)

            if not course_url:
                # 登录后页面可能仍在导航，显式跳转确保页面稳定
                await page.goto(INDEX_URL, wait_until="networkidle")
                ui.info("正在获取课程列表...")
                courses = await fetch_courses(page)
                if not courses:
                    ui.error("获取课程列表失败，请手动指定 --course-url")
                    sys.exit(1)

                grouped = group_by_term(courses)
                term = ui.term_menu(grouped)
                selected = ui.course_menu(grouped[term])
                course_url = build_course_url(selected)
                ui.info(f"已选择: {selected['course']['name']}")

                await page.goto(course_url, wait_until="domcontentloaded")
                await page.get_by_role("tab", name="学习内容").wait_for(timeout=30_000)

            ui.info("正在解析课程目录...")
            frame = await go_to_course_content(page)
            units = await parse_units(frame)
            ui.info(f"找到 {len(units)} 个学习单元")

            todo = [u for u in units if not is_completed(u)]
            ui.info(f"待完成: {len(todo)} 个")
            ui.unit_table(units)

            if not todo:
                ui.success("所有单元已完成!")
                return

            completed_count = 0
            skipped = set()
            while True:
                # Re-parse units each iteration to get fresh locators
                todo = [u for u in units if not is_completed(u) and u.name not in skipped]
                if not todo:
                    break

                unit = todo[0]
                completed_count += 1
                ui.section(f"[{completed_count}/{completed_count + len(todo) - 1}] {unit.name} ({unit.status})")
                try:
                    current_url = page.url
                    await unit.locator.click()
                    try:
                        await page.wait_for_function(
                            "(prev) => window.location.href !== prev",
                            arg=current_url, timeout=10_000,
                        )
                    except (TimeoutError, PlaywrightTimeoutError):
                        await asyncio.sleep(3)

                    content_type = await detect_content_type(page)
                    ui.info(f"内容类型: {content_type}")

                    if content_type == "graph":
                        await handle_graph(page)
                    elif content_type == "video":
                        await handle_video_unit(page, speed, model, api_key, base_url)
                    else:
                        ui.warn("未知内容类型，等待 5 秒后跳过")
                        await asyncio.sleep(5)
                except Exception as e:
                    ui.error(f"处理失败: {type(e).__name__}: {e}，跳过此单元")
                    logger.exception("处理单元失败: %s", unit.name)
                    skipped.add(unit.name)

                ui.info("返回课程目录...")
                try:
                    await page.goto(course_url)
                    await page.wait_for_load_state("domcontentloaded")
                    frame = await go_to_course_content(page)
                    units = await parse_units(frame)
                    todo_remaining = [u for u in units if not is_completed(u)]
                    ui.info(f"剩余未完成: {len(todo_remaining)} 个")
                except Exception as e:
                    ui.error(f"返回目录失败: {type(e).__name__}: {e}")
                    break

            ui.console.print()
            ui.success("[bold]全部学习单元处理完成![/bold]")

        except KeyboardInterrupt:
            ui.console.print()
            ui.warn("用户中断，退出...")
        finally:
            try:
                await save_browser_state(context, state_path)
            except Exception:
                pass
