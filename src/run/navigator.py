"""Course navigation and unit parsing."""

from dataclasses import dataclass
from playwright.async_api import Page, Locator, FrameLocator
from src.core.logger import get_logger
from src import ui

logger = get_logger(__name__)


@dataclass
class LearningUnit:
    name: str
    unit_type: str  # "video" or "graph"
    status: str     # "未开始", "未读", "进行中", "XX%", "已读", "已完成"
    locator: Locator


async def go_to_course_content(page: Page) -> FrameLocator:
    logger.info("进入课程目录")
    await page.get_by_role("tab", name="学习内容").click()
    iframe = page.frame_locator("iframe").first
    await iframe.locator(".leaf-detail").first.wait_for(timeout=30_000)
    return iframe


async def parse_units(frame: FrameLocator) -> list[LearningUnit]:
    units = []
    rows = frame.locator(".leaf-detail")
    count = await rows.count()

    for i in range(count):
        row = rows.nth(i)
        title_el = row.locator(".leaf-title").first
        if await title_el.count() == 0:
            continue
        name = (await title_el.inner_text()).strip()

        icon_el = row.locator(".iconfont").first
        unit_type = "unknown"
        if await icon_el.count() > 0:
            icon_class = await icon_el.get_attribute("class") or ""
            if "icon--shipin" in icon_class:
                unit_type = "video"
            elif "icon--tuwen" in icon_class:
                unit_type = "graph"

        status = ""
        progress_el = row.locator(".progress-wrap").first
        if await progress_el.count() > 0:
            status = (await progress_el.inner_text()).strip()

        units.append(LearningUnit(name=name, unit_type=unit_type, status=status, locator=row))

    if not units:
        ui.warn("未找到任何学习单元，可能页面结构已变化")

    logger.info("解析到 %d 个学习单元", len(units))
    return units


def is_completed(unit: LearningUnit) -> bool:
    return unit.status in ("已读", "已完成", "100%")


async def detect_content_type(page: Page) -> str:
    url = page.url
    if "/xcloud/video-student/" in url:
        return "video"
    elif "/lms/" in url and "/graph/" in url:
        return "graph"
    return "unknown"
