"""Core download logic: navigate report page, extract slide data, download images, assemble PDF."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import img2pdf
from playwright.async_api import BrowserContext, Page
from src.core.logger import get_logger
from src import ui

logger = get_logger(__name__)


def parse_lesson_id(url: str) -> str:
    match = re.search(r"/student-lesson-report/[^/]+/([^/]+)/[^/]+", url)
    if not match:
        raise ValueError(f"Cannot extract lessonId from URL: {url}")
    return match.group(1)


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


@dataclass
class SlideInfo:
    title: str
    covers: list[str] = field(default_factory=list)


async def _extract_slide_info(print_page: Page) -> SlideInfo:
    data = await print_page.evaluate("JSON.parse(localStorage.getItem('rain_print'))")
    if data is None:
        raise RuntimeError("localStorage.rain_print is empty on the print page")
    title = data.get("Title", "untitled")
    slides = sorted(data.get("Slides", []), key=lambda s: s.get("Index", 0))
    covers = [s["Cover"] for s in slides if s.get("Cover")]
    return SlideInfo(title=title, covers=covers)


async def _get_browser_cookies(context: BrowserContext) -> dict[str, str]:
    cookies = await context.cookies()
    return {c["name"]: c["value"] for c in cookies}


async def _download_images(covers: list[str], cookies: dict[str, str]) -> list[bytes]:
    async def _fetch(client: httpx.AsyncClient, url: str) -> bytes:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content

    async with httpx.AsyncClient(cookies=cookies, timeout=60.0) as client:
        tasks = [_fetch(client, url) for url in covers]
        return list(await asyncio.gather(*tasks))


def _save_pdf(images: list[bytes], path: Path) -> None:
    pdf_bytes = img2pdf.convert(images)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    ui.success(f"已保存: {path}")


def _make_filename(
    lesson_title: str,
    pres_title: str,
    lesson_id: str,
    pres_index: int,
    pres_count: int,
) -> str:
    """Build a PDF filename, choosing pres_title for multi-PPT or lesson_title for single."""
    if pres_count > 1:
        name = sanitize_filename(pres_title)
        return f"{name}-{lesson_id}-{pres_index + 1}.pdf"
    return f"{sanitize_filename(lesson_title)}-{lesson_id}.pdf"


async def download_slides_api(
    lesson_id: str,
    lesson_title: str,
    presentations: list,
    output_dir: Path,
) -> list[Path]:
    """Download slides via API (no browser needed).

    Each Presentation object must have .title and .covers attributes.
    Cover URLs contain embedded tokens so no cookies are required.
    """
    pres_count = len(presentations)
    pdf_paths: list[Path] = []

    for i, pres in enumerate(presentations):
        if pres_count > 1:
            ui.info(f"  ({i + 1}/{pres_count}) {pres.title}")
        ui.info(f"  {len(pres.covers)} 页")

        images = await _download_images(pres.covers, cookies={})
        filename = _make_filename(lesson_title, pres.title, lesson_id, i, pres_count)
        pdf_path = output_dir / filename
        _save_pdf(images, pdf_path)
        pdf_paths.append(pdf_path)

    return pdf_paths


async def _handle_multi(
    context: BrowserContext, iframe, lesson_id: str,
    output_dir: Path, cookies: dict[str, str],
) -> list[Path]:
    items = iframe.locator(".ppt-list-item")
    count = await items.count()
    ui.info(f"检测到 {count} 个课件")

    pdf_paths: list[Path] = []
    for i in range(count):
        item = items.nth(i)
        title_text = await item.locator(".ppt-title").inner_text()
        ui.info(f"({i + 1}/{count}) {title_text}")

        page_count_before = len(context.pages)
        await item.locator(".ppt-print").click()

        if len(context.pages) <= page_count_before:
            new_page = await context.wait_for_event("page", timeout=15_000)
        else:
            new_page = context.pages[-1]

        await new_page.wait_for_load_state("domcontentloaded")
        info = await _extract_slide_info(new_page)
        ui.info(f"  {len(info.covers)} 页")

        images = await _download_images(info.covers, cookies)
        filename = f"{sanitize_filename(info.title)}-{lesson_id}.pdf"
        pdf_path = output_dir / filename
        _save_pdf(images, pdf_path)
        pdf_paths.append(pdf_path)

        await new_page.close()

        if i < count - 1:
            print_btn = iframe.locator(".print-btn")
            await print_btn.click()
            await iframe.locator(".ppt-list-item").first.wait_for(timeout=5_000)

    return pdf_paths


async def download_lesson_slides(
    page: Page, url: str, output_dir: str | Path = "output",
) -> list[Path]:
    output_dir = Path(output_dir)
    lesson_id = parse_lesson_id(url)
    context = page.context

    ui.section(f"课件: {lesson_id}")

    await page.goto(url, wait_until="domcontentloaded")
    iframe = page.frame_locator("iframe").first
    await iframe.locator(".left-panel-tab-title").wait_for(timeout=30_000)
    await iframe.locator(".left-panel-tab-title .tab-item").nth(1).click()

    print_btn = iframe.locator(".print-btn")
    await print_btn.wait_for(timeout=10_000)
    await page.wait_for_load_state("networkidle")

    new_page_future: asyncio.Future[Page] = asyncio.get_running_loop().create_future()

    def _on_page(p: Page) -> None:
        if not new_page_future.done():
            new_page_future.set_result(p)

    context.on("page", _on_page)
    try:
        await print_btn.click()

        ppt_items = iframe.locator(".ppt-list-item")
        try:
            await ppt_items.first.wait_for(timeout=3_000)
            is_multi = True
        except Exception:
            is_multi = False

        cookies = await _get_browser_cookies(context)

        if is_multi:
            if new_page_future.done():
                await (await new_page_future).close()
            return await _handle_multi(context, iframe, lesson_id, output_dir, cookies)
        else:
            if not new_page_future.done():
                try:
                    await asyncio.wait_for(new_page_future, timeout=15.0)
                except asyncio.TimeoutError:
                    raise RuntimeError("打印课件未能打开新标签页")
            print_page = new_page_future.result()
            await print_page.wait_for_load_state("domcontentloaded")

            info = await _extract_slide_info(print_page)
            ui.info(f"课件: {info.title} ({len(info.covers)} 页)")

            images = await _download_images(info.covers, cookies)
            filename = f"{sanitize_filename(info.title)}-{lesson_id}.pdf"
            pdf_path = output_dir / filename
            _save_pdf(images, pdf_path)
            await print_page.close()
            return [pdf_path]
    finally:
        context.remove_listener("page", _on_page)
